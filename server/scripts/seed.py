"""Idempotent dev seed (safe to re-run): upserts on natural identifiers.

Run from server/:  .venv/bin/python scripts/seed.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionFactory  # noqa: E402
from app.models import Hostel, Student, User, WardenHostel  # noqa: E402
from app.services.identity import normalize_email  # noqa: E402

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "AdminPass123!"

# Dev-only warden credential. Production wardens are provisioned by an admin
# (POST /admin/wardens) — see docs/API.md. Never reuse these values live.
WARDEN_USERNAME = "warden"
WARDEN_PASSWORD = "WardenPass123!"

HOSTEL_SPEC = {
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

DEPARTMENT = "Computer Science & Engg"
COHORT = "3rd Year (B.Tech 22–26)"

# Enrollment status drives the warden console. The two `active` students keep
# their long-standing dev password so existing walkthroughs still sign in; the
# other two exercise the pending states a warden sees on first use.
STUDENT_SPECS = [
    {"student_id": "CS-2022-084", "name": "Rohan Sharma", "room": "314",
     "email": "cs-2022-084@ceconline.edu", "enrollment_status": "active",
     "password": "student123!"},
    {"student_id": "CS-2022-101", "name": "Arjun Mehta", "room": "315",
     "email": "cs-2022-101@ceconline.edu", "enrollment_status": "active",
     "password": "student123!"},
    # Details confirmed but no face template yet — a status the seed can
    # assert honestly. Deliberately NOT seeded as `face_enrolled` or later:
    # those states imply a real biometric template exists, and a seed must not
    # fabricate one. Walk verify → enroll → activate live in the warden console.
    {"student_id": "CS-2022-117", "name": "Ishaan Verma", "room": "316",
     "email": "cs-2022-117@ceconline.edu",
     "enrollment_status": "details_verified", "password": None},
    # Record created only — details not yet confirmed by the warden.
    {"student_id": "CS-2022-132", "name": "Kabir Nair", "room": "318",
     "email": "cs-2022-132@ceconline.edu",
     "enrollment_status": "created", "password": None},
]


def upsert_admin(db: Session) -> User:
    """One admin identity, password reset to the documented dev value."""
    user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    if user is None:
        user = User(username=ADMIN_USERNAME, role="admin", account_status="active")
        db.add(user)
    user.role = "admin"
    user.account_status = "active"
    user.password_hash = hash_password(ADMIN_PASSWORD)
    return user


def upsert_hostel(db: Session) -> Hostel:
    """Ganga Boys Hostel block B with the full geofence + policy config."""
    hostel = db.scalar(select(Hostel).where(
        Hostel.name == HOSTEL_SPEC["name"], Hostel.block == HOSTEL_SPEC["block"]))
    if hostel is None:
        hostel = Hostel(**HOSTEL_SPEC)
        db.add(hostel)
    else:
        for key, value in HOSTEL_SPEC.items():
            setattr(hostel, key, value)
    db.flush()
    return hostel


def upsert_warden(db: Session, hostel: Hostel) -> User:
    """Dev warden identity + its hostel-scoped authorization grant."""
    user = db.scalar(select(User).where(User.username == WARDEN_USERNAME))
    if user is None:
        user = User(username=WARDEN_USERNAME, role="warden",
                    account_status="active")
        db.add(user)
    user.role = "warden"
    user.account_status = "active"
    user.password_hash = hash_password(WARDEN_PASSWORD)
    db.flush()

    grant = db.scalar(select(WardenHostel).where(
        WardenHostel.user_id == user.id, WardenHostel.hostel_id == hostel.id))
    if grant is None:
        db.add(WardenHostel(user_id=user.id, hostel_id=hostel.id))
    return user


def upsert_student(db: Session, hostel: Hostel, spec: dict) -> Student:
    """Login user (username = roll) + profile row.

    Students are NOT created through the self-service path — the seed mirrors
    exactly what ``services.enrollment.create_student`` writes for each status:
    an ``active`` account carries a usable password, while anything earlier in
    the lifecycle carries the unusable placeholder hash so sign-in stays closed
    until the activation link is redeemed.
    """
    roll = spec["student_id"]
    status = spec.get("enrollment_status", "active")
    password = spec.get("password")
    usable = password is not None

    user = db.scalar(select(User).where(User.username == roll))
    if user is None:
        user = User(username=roll, role="student",
                    account_status="active" if usable else "inactive")
        db.add(user)
    user.role = "student"
    user.account_status = "active" if usable else "inactive"
    if usable:
        user.password_hash = hash_password(password)
    else:
        # Matches enrollment_service._UNSET_PASSWORD_MARKER so
        # has_usable_password() reports False for these rows.
        user.password_hash = hash_password("!not-activated:" + roll)
    db.flush()

    student = db.scalar(select(Student).where(Student.student_id == roll))
    if student is None:
        student = Student(user_id=user.id, student_id=roll)
        db.add(student)
    student.name = spec["name"]
    student.department = DEPARTMENT
    student.cohort = COHORT
    student.room = spec["room"]
    student.hostel_id = hostel.id
    student.enrollment_status = status
    student.email = (normalize_email(spec["email"])
                     if spec.get("email") else None)
    return student


def main() -> None:
    """Seed everything and print the resulting credentials."""
    db = SessionFactory()
    try:
        admin = upsert_admin(db)
        hostel = upsert_hostel(db)
        warden = upsert_warden(db, hostel)
        students = [upsert_student(db, hostel, spec) for spec in STUDENT_SPECS]
        db.commit()
    finally:
        db.close()

    print("HostelPass seed complete (idempotent — re-run any time).")
    print(f"  Admin   : {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print(f"  Warden  : {WARDEN_USERNAME} / {WARDEN_PASSWORD}"
          f"  (granted {HOSTEL_SPEC['name']}, user id {warden.id})")
    for spec in STUDENT_SPECS:
        cred = (f"{spec['password']}" if spec.get("password")
                else "no password until activation link is redeemed")
        note = ("" if spec.get("enrollment_status") == "active"
                else f", status {spec['enrollment_status']}")
        print(f"  Student : {spec['student_id']} / {cred}"
              f"  ({spec['name']}, room {spec['room']}{note})")
    print(f"  Roster  : {len(students)} student records"
          f" (statuses: {', '.join(s['enrollment_status'] for s in STUDENT_SPECS)})")
    print(f"  Hostel  : {HOSTEL_SPEC['name']} block {HOSTEL_SPEC['block']}"
          f" — radius {HOSTEL_SPEC['permitted_radius_m']} m,"
          f" window {HOSTEL_SPEC['window_start']}-{HOSTEL_SPEC['window_end']}"
          f" {HOSTEL_SPEC['timezone']} (admin user id {admin.id})")


if __name__ == "__main__":
    main()
