"""Pytest fixtures — tests run against REAL PostgreSQL (compose `db` on
127.0.0.1:5433). A dedicated test database is dropped/created/migrated once
per session and truncated between tests, so the suite is re-runnable.

The attendance decision clock is frozen at 2026-10-13T15:12:19Z
(= 20:42:19 IST, inside the seeded 20:30-22:30 window) for determinism.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://hostelpass:hostelpass@127.0.0.1:5433/hostelpass_test",
)
# Point the app at the test DB BEFORE any app import (settings are cached).
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Pin the email mode too: the deployment .env may set EMAIL_MODE=log/smtp,
# and tests must not depend on the operator's local configuration. Individual
# tests exercise log/smtp modes explicitly via monkeypatch.
os.environ["EMAIL_MODE"] = "off"

from sqlalchemy import create_engine, text  # noqa: E402

from app.core import clock  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionFactory  # noqa: E402
from app.db.session import engine as app_engine  # noqa: E402
from app.models import Hostel, Student, User, WardenHostel  # noqa: E402
from app.services import geofence  # noqa: E402

# Tuesday 2026-10-13 15:12:19 UTC == 20:42:19 IST (inside 20:30-22:30 window)
FROZEN_NOW = datetime(2026, 10, 13, 15, 12, 19, tzinfo=timezone.utc)

TABLES = (
    "users",
    "students",
    "hostels",
    "face_enrollments",
    "attendance_records",
    "attendance_attempts",
    "audit_logs",
    "revoked_tokens",
    "warden_hostels",
    "account_activation_tokens",
)

DEFAULT_HOSTEL_SPEC = {
    "name": "Ganga Boys Hostel",
    "block": "B",
    "anchor_label": "Ganga Block B",
    "latitude": 12.9716,
    "longitude": 79.1585,
    "permitted_radius_m": 120.0,
    "max_location_accuracy_m": 50.0,
    "boundary_policy": "conservative",
    "timezone": "Asia/Kolkata",
    "window_start": "20:30",
    "window_end": "22:30",
    "require_liveness": True,
    "face_match_threshold": 0.75,
    "warden_name": "Dr. K. Raman",
    "warden_extension": "204",
}


# --------------------------------------------------------------------------
# Database lifecycle
# --------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Drop + create the test database, then run alembic migrations."""
    name = TEST_DATABASE_URL.rsplit("/", 1)[1]
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    def _recreate() -> None:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{name}"'))

    _recreate()

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")

    yield TEST_DATABASE_URL

    app_engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate every table before each test (re-runnable isolation)."""
    _STAFF_CACHE.clear()
    with app_engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    """Freeze the attendance decision clock (tests may re-patch)."""
    monkeypatch.setattr(clock, "utcnow", lambda: FROZEN_NOW)
    yield


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """The in-process limiter must not leak counters across tests."""
    limiter.clear()
    yield
    limiter.clear()


@pytest.fixture
def db():
    """A direct ORM session for seeding/asserting (separate from requests)."""
    session = SessionFactory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# --------------------------------------------------------------------------
# App client
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    from app.main import app as application

    return application


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Factories
# --------------------------------------------------------------------------

@pytest.fixture
def make_hostel(db):
    def _make(**overrides) -> Hostel:
        hostel = Hostel(**{**DEFAULT_HOSTEL_SPEC, **overrides})
        db.add(hostel)
        db.commit()
        db.refresh(hostel)
        return hostel

    return _make


@pytest.fixture
def make_student(db):
    def _make(roll: str = "CS-2022-084", name: str = "Rohan Sharma",
              password: str = "student123!", hostel: Hostel | None = None,
              account_status: str = "active",
              email: str | None = None,
              enrollment_status: str = "active") -> Student:
        user = User(
            username=roll,
            password_hash=hash_password(password),
            role="student",
            account_status=account_status,
        )
        db.add(user)
        db.flush()
        student = Student(
            user_id=user.id,
            student_id=roll,
            name=name,
            # Unique per roll so multi-student tests never collide on the
            # (unique) college-email index.
            email=email if email is not None else f"{roll.lower()}@ceconline.edu",
            enrollment_status=enrollment_status,
            department="Computer Science & Engg",
            cohort="3rd Year (B.Tech 22-26)",
            room="314",
            hostel_id=hostel.id if hostel is not None else None,
        )
        db.add(student)
        db.commit()
        db.refresh(student)
        return student

    return _make


@pytest.fixture
def make_admin(db):
    def _make(username: str = "admin", password: str = "AdminPass123!") -> User:
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            account_status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def make_warden(db, make_hostel):
    def _make(username: str = "warden", password: str = "WardenPass123!",
              hostels: list | None = None) -> User:
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="warden",
            account_status="active",
        )
        db.add(user)
        db.flush()
        grants = hostels if hostels is not None else [make_hostel()]
        for hostel in grants:
            db.add(WardenHostel(user_id=user.id, hostel_id=hostel.id))
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def login(client):
    def _login(student_id: str, password: str) -> str:
        resp = client.post(
            "/api/v1/auth/login",
            json={"student_id": student_id, "password": password},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]

    return _login


@dataclass
class StudentEnv:
    """Hostel + student + valid token, ready for endpoint calls."""

    client: object
    hostel: Hostel
    student: Student
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def student_env(client, make_hostel, make_student, login) -> StudentEnv:
    hostel = make_hostel()
    student = make_student(hostel=hostel)
    token = login(student.student_id, "student123!")
    return StudentEnv(client=client, hostel=hostel, student=student, token=token)


# --------------------------------------------------------------------------
# Payload helpers (importable from test modules)
# --------------------------------------------------------------------------

def base_embedding(dim: int = 128) -> list[float]:
    """Deterministic non-trivial unit-agnostic embedding."""
    return [math.sin(i * 0.7) for i in range(dim)]


def mismatched_embedding(dim: int = 128) -> list[float]:
    """Far from ``base_embedding`` (cosine ~0 => below any sane threshold)."""
    emb = base_embedding(dim)
    return [v if i < dim // 2 else -v for i, v in enumerate(emb)]


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def verify_body(embedding: list[float] | None = None,
                latitude: float = 12.97162,
                longitude: float = 79.15851,
                accuracy_m: float = 4.0,
                age_seconds: float = 5.0,
                liveness: dict | None = None,
                device: bool = True) -> dict:
    """A contract-shaped verify payload (fresh timestamp vs frozen clock)."""
    emb = embedding if embedding is not None else base_embedding()
    live = liveness if liveness is not None else {
        "method": "antispoof_model_v1", "score": 0.012, "passed": True,
    }
    stamp = utc_iso(clock.utcnow() - timedelta(seconds=age_seconds))
    body = {
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy_m": accuracy_m,
            "timestamp_utc": stamp,
        },
        "face": {
            "embedding": emb,
            "embedding_dim": len(emb),
            "model_version": "mobilefacenet_tflite_128_v1",
            "liveness": live,
            "captured_at_utc": stamp,
        },
    }
    if device:
        body["device"] = {
            "app_version": "1.0.0",
            "platform": "android",
            "device_model": "Pixel 8",
            "integrity_verdict": None,
        }
    return body


def enroll(client, headers: dict, embedding: list[float] | None = None) -> list[float]:
    """Enroll a student's face the way production does: a WARDEN does it.

    ``headers`` identify the student (resolved via /auth/me, never trusted for
    authorization); the write itself uses a staff session created on demand,
    because students may not self-enroll. Returns the stored embedding.
    """
    emb = embedding if embedding is not None else base_embedding()
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    roll = me.json()["student_id"]

    resp = client.put(
        f"/api/v1/warden/students/{roll}/face-enrollment",
        headers=staff_headers(client),
        json={"embedding": emb, "embedding_dim": len(emb),
              "model_version": "mobilefacenet_tflite_128_v1"},
    )
    assert resp.status_code == 200, resp.text
    return emb


_STAFF_CACHE: dict[str, str] = {}


def staff_headers(client) -> dict[str, str]:
    """Bearer headers for a fresh admin session (cached per test).

    Cleared by the ``_clean_tables`` autouse fixture, since truncation
    invalidates every previously issued token.
    """
    token = _STAFF_CACHE.get("token")
    if token is None:
        from app.core.security import hash_password as _hp
        from app.db.session import SessionFactory as _SF
        from app.models import User as _U

        with _SF() as session:
            session.add(_U(username="_test_admin", password_hash=_hp("AdminPass123!"),
                           role="admin", account_status="active"))
            session.commit()
        resp = client.post("/api/v1/auth/login",
                           json={"student_id": "_test_admin", "password": "AdminPass123!"})
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        _STAFF_CACHE["token"] = token
    return {"Authorization": f"Bearer {token}"}


def assert_error(resp, status: int, code: str) -> dict:
    """Assert the canonical error envelope: status + machine code + shape."""
    assert resp.status_code == status, f"expected {status}, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "error" in data, data
    assert data["error"]["code"] == code, data
    assert isinstance(data["error"]["message"], str) and data["error"]["message"]
    assert isinstance(data["error"]["details"], dict)
    return data["error"]


def lat_offset_for(distance_m: float, anchor_lat: float = 12.9716) -> float:
    """Latitude that sits ``distance_m`` north of the anchor (same meridian)."""
    return anchor_lat + math.degrees(distance_m / geofence.EARTH_RADIUS_M)
