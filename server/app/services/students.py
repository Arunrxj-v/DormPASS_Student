"""Student-facing service helpers (serialization shared by auth routes)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Student, User
from ..schemas import HostelRef, StudentPublic
from .identity import normalize_email


def build_student_public(user: User, student: Student | None) -> StudentPublic:
    """<StudentPublic> for a user.

    Admins have no student row; the contract still wants a ``student`` object
    in the login response, so it is built from the user identity.
    """
    if student is None:
        return StudentPublic(
            id=user.id,
            student_id=user.username,
            name=user.username,
            email=None,
            enrollment_status=None,
            department=None,
            cohort=None,
            role=user.role,
            account_status=user.account_status,
            hostel=None,
        )
    hostel_ref = None
    if student.hostel is not None:
        hostel_ref = HostelRef(
            id=student.hostel.id,
            name=student.hostel.name,
            block=student.hostel.block,
            room=student.room,
        )
    return StudentPublic(
        id=student.id,
        student_id=student.student_id,
        name=student.name,
        email=student.email,
        enrollment_status=student.enrollment_status,
        department=student.department,
        cohort=student.cohort,
        role=user.role,
        account_status=user.account_status,
        hostel=hostel_ref,
    )


def get_student_by_user(db: Session, user: User) -> Student | None:
    """The student row for a user, if any."""
    return db.scalar(select(Student).where(Student.user_id == user.id))


def find_login_user(db: Session, identifier: str) -> User | None:
    """Resolve a login identifier: college email OR roll number/username.

    Email addresses live on ``students.email`` (the login key for students),
    while wardens/admins sign in with their ``users.username``. Roll-number
    logins stay supported case-insensitively.
    """
    value = identifier.strip()
    if not value:
        return None
    if "@" in value:
        email = normalize_email(value)
        # Staff may have an email-shaped username; students key on students.email.
        user = db.scalar(select(User).where(User.username == email))
        if user is not None:
            return user
        student = db.scalar(select(Student).where(Student.email == email))
        if student is None:
            return None
        return db.get(User, student.user_id)
    return db.scalar(
        select(User).where(func.lower(User.username) == value.lower())
    )
