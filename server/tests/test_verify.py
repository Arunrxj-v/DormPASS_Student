"""POST /attendance/verify — every enforcement step from docs/API.md."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core import clock
from app.models import AuditLog, AttendanceAttempt, AttendanceRecord
from app.services import geofence
from conftest import (
    assert_error,
    base_embedding,
    enroll,
    lat_offset_for,
    mismatched_embedding,
    verify_body,
)

VERIFY = "/api/v1/attendance/verify"
REFERENCE_RE = r"^HP-\d{4}-\d{4}-\d{4}(-[A-Z0-9]{4})?$"


def _post(env, body, token: str | None = None):
    headers = env.headers if token is None else {"Authorization": f"Bearer {token}"}
    return env.client.post(VERIFY, headers=headers, json=body)


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------

def test_verify_happy_path_inside_geofence(student_env, db):
    env = student_env
    emb = enroll(env.client, env.headers)

    resp = _post(env, verify_body(emb))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "present"
    assert data["outcome"] == "verified"
    assert data["date"] == "2026-10-13"
    assert data["reference"] == "HP-2026-1013-2042"  # local HHMM of frozen clock
    import re
    assert re.match(REFERENCE_RE, data["reference"])
    assert data["recorded_at"] == "2026-10-13T15:12:19Z"
    assert data["recorded_at_local"] == "2026-10-13T20:42:19+05:30"
    assert data["distance_m"] is not None and data["distance_m"] < 10
    assert data["accuracy_m"] == 4.0
    assert data["face_similarity"] >= 0.75
    assert data["liveness_method"] == "antispoof_model_v1"
    assert data["liveness_score"] == 0.012
    assert data["gate"] is None
    assert data["reason"] is None
    assert data["id"] is not None

    # Persisted row matches the response and obeys the unique constraint.
    record = db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.student_id == env.student.id))
    assert record is not None
    assert record.reference == data["reference"]
    assert record.attendance_date.isoformat() == "2026-10-13"
    assert record.outcome == "verified"
    assert record.hostel_id == env.hostel.id
    assert record.recorded_at.tzinfo is not None

    # Accepted attempt stored WITHOUT raw coordinates.
    attempt = db.scalar(select(AttendanceAttempt).where(
        AttendanceAttempt.student_id == env.student.id))
    assert attempt is not None
    assert attempt.outcome == "accepted"
    assert attempt.rejection_code is None
    assert attempt.distance_m is not None and attempt.accuracy_m == 4.0
    column_names = {c.name for c in AttendanceAttempt.__table__.columns}
    assert "latitude" not in column_names and "longitude" not in column_names

    # Audit row written on success.
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "attendance.verify"))
    assert audit is not None
    assert audit.actor_label == env.student.student_id
    assert audit.details["reference"] == data["reference"]


# --------------------------------------------------------------------------
# Location gates
# --------------------------------------------------------------------------

def test_verify_outside_geofence(student_env, db):
    env = student_env
    resp = _post(env, verify_body(latitude=13.10, longitude=79.15))
    err = assert_error(resp, 403, "outside_geofence")
    assert err["details"]["distance_m"] > 1000
    assert err["details"]["permitted_radius_m"] == 120.0

    # Rejected attempt persisted with distance but no coordinates.
    attempt = db.scalar(select(AttendanceAttempt).where(
        AttendanceAttempt.student_id == env.student.id))
    assert attempt is not None
    assert attempt.outcome == "rejected"
    assert attempt.rejection_code == "outside_geofence"
    assert attempt.distance_m is not None
    assert db.scalar(select(AttendanceRecord)) is None


def test_verify_accuracy_too_poor_is_unusable(student_env):
    env = student_env
    resp = _post(env, verify_body(accuracy_m=80.0))  # > max_location_accuracy_m (50)
    err = assert_error(resp, 422, "location_unusable")
    assert err["details"]["max_location_accuracy_m"] == 50.0
    assert err["details"]["accuracy_m"] == 80.0


def test_verify_zero_accuracy_is_unusable(student_env):
    resp = _post(student_env, verify_body(accuracy_m=0.0))
    assert_error(resp, 422, "location_unusable")


def test_verify_stale_timestamp_is_stale(student_env):
    resp = _post(student_env, verify_body(age_seconds=300.0))
    err = assert_error(resp, 422, "location_stale")
    assert err["details"]["age_seconds"] > 90
    assert err["details"]["max_age_seconds"] == 90


def test_verify_freshness_boundary_90s_ok(student_env):
    """Exactly at the 90 s limit passes freshness (fails later at enrollment)."""
    resp = _post(student_env, verify_body(age_seconds=90.0))
    # 90 s is fresh; this student is not enrolled -> face_not_enrolled.
    assert_error(resp, 403, "face_not_enrolled")


def test_geofence_conservative_boundary(client, db):
    """distance + accuracy exactly == radius passes; just beyond fails."""
    from app.core.security import hash_password
    from app.models import Hostel, Student, User

    hostel = Hostel(**{
        "name": "Boundary Hostel", "block": "X",
        "latitude": 12.9716, "longitude": 79.1585,
        "permitted_radius_m": 100.0, "max_location_accuracy_m": 120.0,
        "boundary_policy": "conservative", "timezone": "Asia/Kolkata",
        "window_start": "20:30", "window_end": "22:30",
        "require_liveness": True, "face_match_threshold": 0.75,
    })
    db.add(hostel)
    db.commit()
    db.refresh(hostel)

    def make_user_and_login(roll: str) -> dict:
        user = User(username=roll, password_hash=hash_password("student123!"),
                    role="student", account_status="active")
        db.add(user)
        db.flush()
        db.add(Student(user_id=user.id, student_id=roll, name=roll,
                       email=f"{roll.lower()}@ceconline.edu",
                       enrollment_status="active",
                       hostel_id=hostel.id))
        db.commit()
        resp = client.post("/api/v1/auth/login",
                           json={"student_id": roll, "password": "student123!"})
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    # Exact equality at zero distance: 0.0 + 100.0 <= 100.0 -> passes.
    exact_headers = make_user_and_login("CS-2022-B1")
    enroll(client, exact_headers)
    resp = client.post(VERIFY, headers=exact_headers, json=verify_body(
        latitude=12.9716, longitude=79.1585, accuracy_m=100.0))
    assert resp.status_code == 200, resp.text

    # Just beyond at zero distance: 0.0 + 100.0001 > 100.0 -> rejected.
    beyond_headers = make_user_and_login("CS-2022-B2")
    enroll(client, beyond_headers)
    resp = client.post(VERIFY, headers=beyond_headers, json=verify_body(
        latitude=12.9716, longitude=79.1585, accuracy_m=100.0001))
    err = assert_error(resp, 403, "outside_geofence")
    assert err["details"]["permitted_radius_m"] == 100.0

    # Distance ~40 m: 40 + 59.9 <= 100 passes, 40 + 60.1 > 100 fails.
    near_headers = make_user_and_login("CS-2022-B3")
    enroll(client, near_headers)
    resp = client.post(VERIFY, headers=near_headers, json=verify_body(
        latitude=lat_offset_for(40.0), longitude=79.1585, accuracy_m=60.1))
    assert_error(resp, 403, "outside_geofence")

    far_headers = make_user_and_login("CS-2022-B4")
    enroll(client, far_headers)
    resp = client.post(VERIFY, headers=far_headers, json=verify_body(
        latitude=lat_offset_for(40.0), longitude=79.1585, accuracy_m=59.9))
    assert resp.status_code == 200, resp.text


def test_conservative_policy_unit():
    """The policy itself: whole uncertainty circle must fit the radius."""
    assert geofence.is_inside_conservative(100.0, 0.0, 100.0) is True
    assert geofence.is_inside_conservative(100.0, 0.001, 100.0) is False
    assert geofence.is_inside_conservative(99.5, 0.5, 100.0) is True
    assert geofence.haversine_m(0.0, 0.0, 0.0, 0.0) == 0.0


# --------------------------------------------------------------------------
# Face gates
# --------------------------------------------------------------------------

def test_verify_face_not_enrolled(student_env):
    resp = _post(student_env, verify_body())
    assert_error(resp, 403, "face_not_enrolled")


def test_verify_face_mismatch(student_env, db):
    env = student_env
    enroll(env.client, env.headers, base_embedding())
    resp = _post(env, verify_body(mismatched_embedding()))
    err = assert_error(resp, 403, "face_mismatch")
    assert err["details"]["similarity"] is not None
    assert err["details"]["similarity"] < 0.75

    attempt = db.scalar(select(AttendanceAttempt).where(
        AttendanceAttempt.student_id == env.student.id))
    assert attempt.rejection_code == "face_mismatch"


def test_verify_dim_mismatch_is_face_mismatch(student_env):
    env = student_env
    enroll(env.client, env.headers, base_embedding(128))
    body = verify_body(base_embedding(64))  # stored dim is 128
    resp = _post(env, body)
    err = assert_error(resp, 403, "face_mismatch")
    assert err["details"]["reason"] == "embedding_dim_mismatch"
    assert err["details"]["expected_dim"] == 128


def test_verify_nonfinite_embedding_is_face_mismatch(student_env):
    env = student_env
    enroll(env.client, env.headers, base_embedding())
    body = verify_body(base_embedding())
    body["face"]["embedding"][7] = float("nan")
    # httpx refuses to JSON-encode NaN (allow_nan=False) — send the literal.
    import json as _json

    resp = env.client.post(
        VERIFY,
        headers={**env.headers, "Content-Type": "application/json"},
        content=_json.dumps(body),
    )
    err = assert_error(resp, 403, "face_mismatch")
    assert err["details"]["reason"] == "non_finite_embedding"


# --------------------------------------------------------------------------
# Liveness policy
# --------------------------------------------------------------------------

def test_verify_liveness_failed_high_score(student_env):
    env = student_env
    enroll(env.client, env.headers)
    resp = _post(env, verify_body(liveness={
        "method": "antispoof_model_v1", "score": 0.9, "passed": True}))
    err = assert_error(resp, 403, "liveness_failed")
    assert err["details"]["score"] == 0.9


def test_verify_liveness_failed_flag_or_method(student_env):
    env = student_env
    enroll(env.client, env.headers)
    resp = _post(env, verify_body(liveness={
        "method": "antispoof_model_v1", "score": 0.01, "passed": False}))
    assert_error(resp, 403, "liveness_failed")

    resp = _post(env, verify_body(liveness={
        "method": "blink_heuristic", "score": 0.01, "passed": True}))
    assert_error(resp, 403, "liveness_failed")


def test_verify_without_liveness_requirement_is_pending_review(db, client):
    from app.core.security import hash_password
    from app.models import Hostel, Student, User

    hostel = Hostel(**{
        "name": "NoLiveness Hostel", "block": "A",
        "latitude": 12.9716, "longitude": 79.1585,
        "permitted_radius_m": 120.0, "max_location_accuracy_m": 50.0,
        "boundary_policy": "conservative", "timezone": "Asia/Kolkata",
        "window_start": "20:30", "window_end": "22:30",
        "require_liveness": False, "face_match_threshold": 0.75,
    })
    db.add(hostel)
    user = User(username="CS-2022-050", password_hash=hash_password("student123!"),
                role="student", account_status="active")
    db.add(user)
    db.flush()
    db.add(Student(user_id=user.id, student_id="CS-2022-050", name="Pending Pat",
                   email="cs-2022-050@ceconline.edu", enrollment_status="active",
                   hostel_id=hostel.id))
    db.commit()
    student = db.scalar(select(Student).where(Student.student_id == "CS-2022-050"))

    token = client.post("/api/v1/auth/login", json={
        "student_id": "CS-2022-050", "password": "student123!"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    emb = enroll(client, headers)

    # Bad liveness is never silently "verified".
    resp = client.post(VERIFY, headers=headers, json=verify_body(emb, liveness={
        "method": "antispoof_model_v1", "score": 0.9, "passed": False}))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "pending_review"
    assert data["status"] == "pending"

    record = db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.student_id == student.id))
    assert record is not None
    assert record.outcome == "pending_review"


# --------------------------------------------------------------------------
# Duplicate prevention (+ concurrency lives in test_verify_concurrent.py)
# --------------------------------------------------------------------------

def test_verify_duplicate_attendance(student_env, db):
    env = student_env
    emb = enroll(env.client, env.headers)

    first = _post(env, verify_body(emb))
    assert first.status_code == 200, first.text

    second = _post(env, verify_body(emb))
    assert_error(second, 409, "duplicate_attendance")

    records = db.scalars(select(AttendanceRecord).where(
        AttendanceRecord.student_id == env.student.id)).all()
    assert len(records) == 1  # unique constraint held

    attempts = db.scalars(select(AttendanceAttempt).where(
        AttendanceAttempt.student_id == env.student.id)).all()
    codes = sorted(a.rejection_code or "accepted" for a in attempts)
    assert codes == ["accepted", "duplicate_attendance"]
    assert len(db.scalars(select(AttendanceRecord)).all()) == 1


# --------------------------------------------------------------------------
# Window / account gates
# --------------------------------------------------------------------------

def test_verify_window_closed(student_env, monkeypatch):
    env = student_env
    enroll(env.client, env.headers)
    # 12:00 UTC = 17:30 IST — outside the 20:30-22:30 window.
    monkeypatch.setattr(clock, "utcnow",
                        lambda: datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc))
    resp = _post(env, verify_body())
    err = assert_error(resp, 403, "attendance_window_closed")
    assert err["details"]["window"]["open"] is False
    assert err["details"]["window"]["timezone"] == "Asia/Kolkata"


def test_verify_inactive_account(student_env, db):
    env = student_env
    enroll(env.client, env.headers)
    env.student.user.account_status = "inactive"
    db.commit()

    resp = _post(env, verify_body())
    assert_error(resp, 403, "account_inactive")


def test_verify_hostel_not_configured(client, make_student, login):
    make_student(roll="CS-2022-077")  # no hostel assigned
    token = login("CS-2022-077", "student123!")
    resp = client.post(VERIFY, headers={"Authorization": f"Bearer {token}"},
                       json=verify_body())
    assert_error(resp, 403, "hostel_not_configured")


# --------------------------------------------------------------------------
# Rate limit + payload validation
# --------------------------------------------------------------------------

def test_verify_rate_limit_10_per_minute(student_env):
    env = student_env
    statuses = []
    for _ in range(11):
        statuses.append(_post(env, verify_body()).status_code)
    # First ten reach the pipeline (403: not enrolled), the 11th is limited.
    assert statuses[:10] == [403] * 10
    assert statuses[10] == 429
    resp = _post(env, verify_body())
    assert_error(resp, 429, "rate_limited")


def test_verify_invalid_payloads(student_env):
    env = student_env
    cases = [
        {},  # missing location + face
        {"location": {"latitude": 1.0, "longitude": 1.0, "accuracy_m": 4.0,
                      "timestamp_utc": "2026-10-13T15:12:00Z"}},  # missing face
        {"location": {"latitude": 1.0, "longitude": 1.0, "timestamp_utc":
                      "2026-10-13T15:12:00Z"},  # missing accuracy_m
         "face": {"embedding": [0.1], "embedding_dim": 1,
                  "liveness": {"method": "m", "score": 0.0, "passed": True}}},
        {"location": {"latitude": "north", "longitude": 1.0, "accuracy_m": 4.0,
                      "timestamp_utc": "2026-10-13T15:12:00Z"},  # bad type
         "face": {"embedding": [0.1], "embedding_dim": 1,
                  "liveness": {"method": "m", "score": 0.0, "passed": True}}},
        {"location": {"latitude": 1.0, "longitude": 1.0, "accuracy_m": 4.0,
                      "timestamp_utc": "2026-10-13T15:12:00"},  # naive timestamp
         "face": {"embedding": [0.1], "embedding_dim": 1,
                  "liveness": {"method": "m", "score": 0.0, "passed": True}}},
        {"location": {"latitude": 1.0, "longitude": 1.0, "accuracy_m": 4.0,
                      "timestamp_utc": "2026-10-13T15:12:00Z"},
         "face": {"embedding": [0.1, 0.2], "embedding_dim": 1,  # length != dim
                  "liveness": {"method": "m", "score": 0.0, "passed": True}}},
    ]
    for body in cases:
        resp = env.client.post(VERIFY, headers=env.headers, json=body)
        assert_error(resp, 400, "invalid_payload")
