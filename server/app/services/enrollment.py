"""Student account provisioning — create, lifecycle transitions, activation.

One implementation shared by ``/admin/students`` and ``/warden/students`` so
both paths apply identical validation, uniqueness rules and audit events.

Lifecycle::

    created -> details_verified -> face_enrolled -> account_provisioned -> active
                                                                    (suspended)

An account can never jump to ``active``: activation additionally requires a
redeemed token, which itself requires ``account_provisioned``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.errors import AppError, conflict, forbidden, not_found
from ..core.roles import (
    STATUS_ACCOUNT_PROVISIONED,
    STATUS_ACTIVE,
    STATUS_CREATED,
    STATUS_DETAILS_VERIFIED,
    STATUS_FACE_ENROLLED,
    STATUS_SUSPENDED,
)
from ..core.security import hash_password, verify_password
from ..models import FaceEnrollment, Hostel, Student, User
from ..schemas import StudentPublic
from .audit import write_audit
from .identity import validate_college_email
from .rooms import validate_student_room
from .students import build_student_public


# --------------------------------------------------------------------------
# Creation
# --------------------------------------------------------------------------

def create_student(
    db: Session,
    *,
    payload: Any,
    actor: User,
    hostel_scoped: bool = False,
) -> StudentPublic:
    """Create a student record + login identity in ONE transaction.

    ``hostel_scoped`` forces a warden to place the student in one of their own
    hostels; admins may create unassigned students.
    """
    roll = payload.student_id.strip()
    email = validate_college_email(payload.email)  # raises -> 400/422

    hostel: Hostel | None = None
    if payload.hostel_id is not None:
        hostel = db.get(Hostel, payload.hostel_id)
        if hostel is None:
            raise not_found("Hostel")
    if hostel_scoped:
        from .authorization import can_manage_hostel

        if not can_manage_hostel(db, actor, payload.hostel_id):
            raise forbidden("You are not authorized for this hostel.")
    # A room must exist in the hostel's registry when that hostel has one.
    validate_student_room(db, hostel_id=payload.hostel_id, room=payload.room)

    # --- uniqueness (both natural keys, case-insensitive) -------------------
    if db.scalar(select(User.id).where(func.lower(User.username) == roll.lower())):
        raise conflict("Student id already exists.")
    if db.scalar(select(Student.id).where(Student.student_id == roll)):
        raise conflict("Student id already exists.")
    if db.scalar(select(Student.id).where(Student.email == email)):
        raise conflict("A student with this college email already exists.")

    # username: students may sign in with either roll or email; store the roll
    # as the login key (emails resolve through students.email).
    user = User(
        username=roll,
        # Unusable placeholder — no staff-chosen passwords. The student sets
        # their real password via the activation token.
        password_hash=hash_password(_UNSET_PASSWORD_MARKER + roll),
        role="student",
        account_status="inactive",
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("Student id already exists.") from exc

    student = Student(
        user_id=user.id,
        student_id=roll,
        name=payload.name.strip(),
        email=email,
        enrollment_status=STATUS_CREATED,
        department=payload.department,
        cohort=payload.cohort,
        room=payload.room,
        hostel_id=payload.hostel_id,
    )
    db.add(student)
    write_audit(
        db,
        actor_user_id=actor.id,
        actor_label=actor.username,
        action="student.create",
        target_type="student",
        target_id=roll,
        details={
            "name": student.name,
            "email": email,
            "hostel_id": str(payload.hostel_id) if payload.hostel_id else None,
            "room": payload.room,
            "status": STATUS_CREATED,
        },
    )
    db.flush()
    db.refresh(student)
    return build_student_public(student.user, student)


# Marker prefix so a pre-activation password can never verify true, even if a
# hash were somehow copied: verify_password() compares against a bcrypt hash of
# this prefixed string, which no caller can produce from a chosen input.
_UNSET_PASSWORD_MARKER = "!not-activated:"


def has_usable_password(password_hash: str, roll: str) -> bool:
    """True when the account no longer carries its unusable placeholder hash."""
    if not password_hash:
        return False
    return not verify_password(_UNSET_PASSWORD_MARKER + roll, password_hash)


# --------------------------------------------------------------------------
# Lifecycle transitions
# --------------------------------------------------------------------------

def _advance(student: Student, target: str) -> None:
    student.enrollment_status = target


def mark_details_verified(db: Session, student: Student, actor: User) -> Student:
    """created -> details_verified (warden confirms the submitted details)."""
    if student.enrollment_status != STATUS_CREATED:
        raise AppError(409, "invalid_transition",
                       f"Cannot verify details from status '{student.enrollment_status}'.")
    _advance(student, STATUS_DETAILS_VERIFIED)
    write_audit(
        db,
        actor_user_id=actor.id,
        actor_label=actor.username,
        action="student.details_verified",
        target_type="student",
        target_id=str(student.id),
        details={"roll": student.student_id},
    )
    db.flush()
    return student


def record_face_enrollment(db: Session, student: Student, actor: User, *,
                           model_version: str, replaced: bool) -> None:
    """Advance the lifecycle after a template was stored (or re-stored).

    Enrollment implies the warden already confirmed the details, so an
    unverified record moves straight to FACE_ENROLLED.
    """
    if student.enrollment_status in (STATUS_CREATED, STATUS_DETAILS_VERIFIED):
        student.enrollment_status = STATUS_FACE_ENROLLED
    write_audit(
        db,
        actor_user_id=actor.id,
        actor_label=actor.username,
        action="face_enrollment.re_enroll" if replaced else "face_enrollment.enroll",
        target_type="student",
        target_id=str(student.id),
        details={"roll": student.student_id, "model_version": model_version},
    )


def provision_account(db: Session, student: Student, actor: User) -> Student:
    """face_enrolled -> account_provisioned (ready for an activation link)."""
    if student.enrollment_status == STATUS_ACCOUNT_PROVISIONED:
        return student  # idempotent re-issue
    if student.enrollment_status != STATUS_FACE_ENROLLED:
        raise AppError(
            409, "not_ready_to_provision",
            "Details must be verified and the student's face enrolled first.",
        )
    student.enrollment_status = STATUS_ACCOUNT_PROVISIONED
    write_audit(
        db,
        actor_user_id=actor.id,
        actor_label=actor.username,
        action="student.provision",
        target_type="student",
        target_id=str(student.id),
        details={"roll": student.student_id},
    )
    db.flush()
    return student


def suspend_student(db: Session, student: Student, actor: User) -> Student:
    """Freeze a student: no login, no attendance. Recoverable by unsuspend."""
    if student.enrollment_status == STATUS_SUSPENDED:
        return student
    if student.enrollment_status == STATUS_CREATED:
        raise AppError(409, "invalid_transition",
                       "A student that has not been provisioned cannot be suspended.")
    student.user.account_status = "inactive"
    write_audit(
        db,
        actor_user_id=actor.id,
        actor_label=actor.username,
        action="student.suspend",
        target_type="student",
        target_id=str(student.id),
        details={"roll": student.student_id,
                 "previous_status": student.enrollment_status},
    )
    # Preserve the pre-suspension status in memory on the row via account flag
    # only; the resume path restores ACTIVE or the provisioned state.
    student.enrollment_status = STATUS_SUSPENDED
    db.flush()
    return student


def unsuspend_student(db: Session, student: Student, actor: User) -> Student:
    """Reverse a suspension: back to ACTIVE (they were active) or provisioned."""
    if student.enrollment_status != STATUS_SUSPENDED:
        raise AppError(409, "invalid_transition",
                       "This account is not suspended.")
    has_template = db.scalar(
        select(FaceEnrollment.id).where(FaceEnrollment.student_id == student.id)
    )
    # A real password (not the unusable placeholder written at creation) is the
    # server-side proof the student completed setup — restore them to ACTIVE.
    live = has_usable_password(student.user.password_hash, student.student_id)
    if live:
        restored = STATUS_ACTIVE
    elif has_template is None:
        restored = STATUS_DETAILS_VERIFIED  # awaiting face enrollment
    else:
        restored = STATUS_ACCOUNT_PROVISIONED
    student.enrollment_status = restored
    student.user.account_status = "active" if live else "inactive"
    write_audit(
        db,
        actor_user_id=actor.id,
        actor_label=actor.username,
        action="student.unsuspend",
        target_type="student",
        target_id=str(student.id),
        details={"roll": student.student_id, "restored_status": student.enrollment_status},
    )
    db.flush()
    return student


def delete_face_enrollment(db: Session, student: Student, actor: User) -> bool:
    """Authorized biometric deletion + lifecycle rollback (recoverable state)."""
    row = db.scalar(select(FaceEnrollment).where(FaceEnrollment.student_id == student.id))
    if row is None:
        return False
    write_audit(
        db,
        actor_user_id=actor.id,
        actor_label=actor.username,
        action="face_enrollment.delete",
        target_type="student",
        target_id=str(student.id),
        details={"model_version": row.model_version, "roll": student.student_id},
    )
    db.delete(row)
    db.flush()
    if student.enrollment_status in (STATUS_FACE_ENROLLED, STATUS_ACCOUNT_PROVISIONED):
        student.enrollment_status = STATUS_DETAILS_VERIFIED
        if student.user.account_status == "active":
            # They could previously sign in; without a template attendance would
            # always fail, so pull them back to pending rather than pretend.
            student.user.account_status = "inactive"
    db.flush()
    return True
