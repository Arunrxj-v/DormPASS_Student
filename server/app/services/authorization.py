"""Hostel-scoped authorization for staff (admin/warden) operations.

Rules enforced here (never in the client):
  * Admins may manage every hostel.
  * Wardens may only manage hostels granted via ``warden_hostels``.
  * A student row belongs to exactly one hostel; staff may only touch students
    whose hostel they are authorized for (admins bypass the check).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import forbidden, not_found
from ..core.roles import ROLE_ADMIN, ROLE_WARDEN
from ..models import Hostel, Student, User, WardenHostel


def is_admin(user: User) -> bool:
    return user.role == ROLE_ADMIN


def is_staff(user: User) -> bool:
    return user.role in {ROLE_ADMIN, ROLE_WARDEN}


def managed_hostel_ids(db: Session, user: User) -> set[UUID] | None:
    """Hostel ids ``user`` may manage. ``None`` means "all" (admins only)."""
    if is_admin(user):
        return None
    rows = db.scalars(select(WardenHostel.hostel_id).where(WardenHostel.user_id == user.id)).all()
    return set(rows)


def can_manage_hostel(db: Session, user: User, hostel_id: UUID | None) -> bool:
    """True when ``user`` may act on students of ``hostel_id``.

    A student with no hostel is only manageable by an admin — a warden with no
    hostel grant must not be able to sweep unassigned students.
    """
    allowed = managed_hostel_ids(db, user)
    if allowed is None:
        return True
    if hostel_id is None:
        return False
    return hostel_id in allowed


def require_staff(user: User) -> None:
    """Raise 403 unless ``user`` is an admin or warden."""
    if not is_staff(user):
        raise forbidden("This action requires a warden or administrator account.")


def require_hostel_access(db: Session, user: User, hostel_id: UUID | None) -> None:
    """Raise 403 when ``user`` may not manage ``hostel_id``."""
    require_staff(user)
    if not can_manage_hostel(db, user, hostel_id):
        raise forbidden("You are not authorized for this hostel.")


def accessible_students_query(db: Session, user: User):
    """Select students ``user`` is allowed to see, ordered by roll number."""
    query = select(Student).order_by(Student.student_id)
    allowed = managed_hostel_ids(db, user)
    if allowed is None:
        return query
    if not allowed:
        # A warden with no hostel grants sees nothing rather than everything.
        return query.where(Student.hostel_id.is_(None), False)
    return query.where(Student.hostel_id.in_(allowed))


def require_student_access(db: Session, user: User, student: Student) -> None:
    """Raise 403 when ``user`` may not manage this specific student."""
    require_hostel_access(db, user, student.hostel_id)


def resolve_hostel_or_404(db: Session, hostel_id: UUID) -> Hostel:
    hostel = db.get(Hostel, hostel_id)
    if hostel is None:
        raise not_found("Hostel")
    return hostel
