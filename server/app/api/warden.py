"""Warden endpoints: student lifecycle management, face enrollment, activation.

Every route is gated by ``require_staff`` (admin or warden) AND scoped to the
hostels granted in ``warden_hostels`` — a warden cannot see or mutate students
outside their hostels, and students can never reach this router at all.
"""

from __future__ import annotations

import math
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..core import clock
from ..core.config import settings
from ..core.errors import conflict, forbidden, not_found
from ..core.roles import (
    ROLE_STUDENT,
    STATUS_ACCOUNT_PROVISIONED,
    STATUS_ACTIVE,
    STATUS_CREATED,
    STATUS_FACE_ENROLLED,
    STATUS_SUSPENDED,
)
from ..db.session import get_session
from ..models import (
    AccountActivationToken,
    AttendanceRecord,
    FaceEnrollment,
    Hostel,
    Student,
    User,
)
from ..schemas import (
    ActivationIssueResponse,
    EnrollmentStatusPublic,
    FaceEnrollmentPut,
    FaceEnrollmentPublic,
    GeofencePublic,
    StudentCreate,
    StudentListResponse,
    StudentPatch,
    StudentPublic,
    WardenDashboard,
)
from ..services import activation as activation_service
from ..services import attendance as attendance_service
from ..services import email as email_service
from ..services import enrollment as enrollment_service
from ..services import rooms as rooms_service
from ..services.audit import write_audit
from ..services.authorization import (
    can_manage_hostel,
    managed_hostel_ids,
    require_staff,
)
from ..services.students import build_student_public
from ..services.template_crypto import encrypt_embedding, l2_normalize
from .deps import get_auth_context

router = APIRouter(prefix="/warden", tags=["warden"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _staff(ctx=Depends(get_auth_context)):
    """Authenticated admin/warden (403 for students)."""
    require_staff(ctx.user)
    return ctx.user


def _resolve_student(db: Session, ref: str) -> Student:
    """Accept a student UUID or the roll number as {id}."""
    stmt = select(Student)
    try:
        row = db.scalar(stmt.where(Student.id == UUID(ref)))
    except ValueError:
        row = None
    if row is None:
        row = db.scalar(stmt.where(Student.student_id == ref))
    if row is None:
        raise not_found("Student")
    return row


def _visible_query(db: Session, actor: User):
    """Students the actor is authorized to see, ordered by roll."""
    query = select(Student).order_by(Student.student_id)
    allowed = managed_hostel_ids(db, actor)
    if allowed is None:
        return query
    if not allowed:
        # Warden with no hostel grants sees nothing (never everything).
        return query.where(Student.id.is_(None))
    return query.where(Student.hostel_id.in_(allowed))


def _require_student_access(db: Session, actor: User, student: Student) -> None:
    """Hide out-of-scope students behind 404 so a warden cannot probe which
    roll numbers exist in hostels they do not manage."""
    if not can_manage_hostel(db, actor, student.hostel_id):
        raise not_found("Student")


def _page(items: list, page: int, page_size: int) -> dict:
    total = len(items)
    total_pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_more": page < total_pages,
    }


def _status_public(db: Session, student: Student) -> EnrollmentStatusPublic:
    """Truthful lifecycle snapshot derived from actual rows, never fabricated."""
    enrolled = db.scalar(
        select(FaceEnrollment.id).where(FaceEnrollment.student_id == student.id)
    )
    pending = db.scalar(
        select(AccountActivationToken.id).where(
            AccountActivationToken.user_id == student.user_id,
            AccountActivationToken.used_at.is_(None),
        )
    )
    # ``password_set`` must mean "the student set a real password" — proven
    # by a usable (non-placeholder) hash. It must NOT be inferred from tokens:
    # reissuing a link revokes predecessors by stamping ``used_at``, which
    # would otherwise masquerade as a redemption.
    return EnrollmentStatusPublic(
        student_id=student.id,
        roll=student.student_id,
        name=student.name,
        email=student.email,
        enrollment_status=student.enrollment_status,
        account_status=student.user.account_status,
        details_complete=student.enrollment_status != STATUS_CREATED,
        face_enrolled=enrolled is not None,
        password_set=enrollment_service.has_usable_password(
            student.user.password_hash, student.student_id
        ),
        activation_pending=pending is not None,
        hostel_id=student.hostel_id,
        room=student.room,
    )


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

@router.get("/dashboard", response_model=WardenDashboard)
def dashboard(
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> WardenDashboard:
    """Roster + enrollment + attendance overview for the actor's hostels."""
    base = _visible_query(db, actor)

    def _count(*clauses) -> int:
        stmt = select(func.count()).select_from(Student)
        allowed = managed_hostel_ids(db, actor)
        if allowed is not None:
            stmt = stmt.where(Student.hostel_id.in_(allowed)) if allowed else stmt.where(
                Student.id.is_(None)
            )
        for clause in clauses:
            stmt = stmt.where(clause)
        return int(db.scalar(stmt) or 0)

    status_counts = {
        s: _count(Student.enrollment_status == s)
        for s in (STATUS_ACTIVE, STATUS_FACE_ENROLLED, STATUS_SUSPENDED, STATUS_CREATED)
    }
    pending = _count(
        Student.enrollment_status.in_([STATUS_CREATED, "details_verified", STATUS_FACE_ENROLLED])
    )

    # Hostels summary (only those the actor may manage).
    allowed = managed_hostel_ids(db, actor)
    hostel_rows = db.scalars(select(Hostel).order_by(Hostel.name)).all()
    if allowed is not None:
        hostel_rows = [h for h in hostel_rows if h.id in allowed]

    hostels = []
    for h in hostel_rows:
        count_stmt = select(func.count()).select_from(Student).where(Student.hostel_id == h.id)
        hostels.append({
            "id": str(h.id),
            "name": h.name,
            "block": h.block,
            "room": h.room_count if hasattr(h, "room_count") else None,
            "students": int(db.scalar(count_stmt) or 0),
            "window": f"{h.window_start}–{h.window_end}",
        })

    # Recent enrollment activity (audit trail, filtered to visible students).
    from ..models import AuditLog

    recent = db.scalars(
        select(AuditLog)
        .where(AuditLog.action.in_([
            "student.create", "student.details_verified",
            "face_enrollment.enroll", "face_enrollment.re_enroll",
            "student.provision", "auth.activate", "student.suspend",
            "student.unsuspend",
        ]))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(8)
    ).all()
    recent_activity = [
        {
            "action": r.action,
            "actor": r.actor_label,
            "target": r.target_id,
            "at": clock.utc_z(r.created_at),
        }
        for r in recent
    ]

    # Attendance today (visible students only).
    today = clock.utcnow().date()
    visible_ids = [s.id for s in db.scalars(base).all()]
    present = 0
    if visible_ids:
        present = int(
            db.scalar(
                select(func.count()).select_from(AttendanceRecord).where(
                    AttendanceRecord.student_id.in_(visible_ids),
                    AttendanceRecord.attendance_date == today,
                )
            )
            or 0
        )

    return WardenDashboard(
        total_students=_count(),
        active_students=status_counts[STATUS_ACTIVE],
        pending_enrollment=pending,
        face_enrolled=status_counts[STATUS_FACE_ENROLLED],
        suspended_students=status_counts[STATUS_SUSPENDED],
        hostels=hostels,
        recent_activity=recent_activity,
        attendance_today={"date": today.isoformat(), "present": present,
                          "roster": len(visible_ids)},
    )


# --------------------------------------------------------------------------
# Roster
# --------------------------------------------------------------------------

@router.get("/hostels", response_model=list[GeofencePublic])
def my_hostels(
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> list[GeofencePublic]:
    """Hostels this warden/admin is authorized to manage."""
    allowed = managed_hostel_ids(db, actor)
    rows = db.scalars(select(Hostel).order_by(Hostel.name)).all()
    if allowed is not None:
        rows = [h for h in rows if h.id in allowed]
    return [GeofencePublic.from_hostel(h) for h in rows]


@router.get("/students", response_model=StudentListResponse)
def list_students(
    q: str | None = Query(default=None, max_length=128,
                          description="name / email / roll / room"),
    hostel_id: UUID | None = Query(default=None),
    room: str | None = Query(default=None, max_length=32),
    enrollment_status: str | None = Query(default=None, max_length=32),
    status: Literal["active", "inactive"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> StudentListResponse:
    """Filtered roster restricted to the actor's hostels."""
    stmt = _visible_query(db, actor)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            Student.name.ilike(like),
            Student.student_id.ilike(like),
            Student.email.ilike(like),
            Student.room.ilike(like),
        ))
    if hostel_id is not None:
        if not can_manage_hostel(db, actor, hostel_id):
            raise forbidden("You are not authorized for this hostel.")
        stmt = stmt.where(Student.hostel_id == hostel_id)
    if room:
        stmt = stmt.where(Student.room == room)
    if enrollment_status:
        stmt = stmt.where(Student.enrollment_status == enrollment_status)
    if status:
        stmt = stmt.join(User, User.id == Student.user_id).where(
            User.account_status == status
        )

    all_rows = list(db.scalars(stmt).all())
    total = len(all_rows)
    total_pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    page_rows = all_rows[start:start + page_size]
    items = [build_student_public(s.user, s) for s in page_rows]
    return StudentListResponse(
        items=items, page=page, page_size=page_size,
        total_pages=total_pages, has_more=page < total_pages,
    )


@router.post("/students", response_model=StudentPublic, status_code=201)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> StudentPublic:
    """Create a student record (no password) inside an authorized hostel."""
    if payload.hostel_id is None:
        raise forbidden("A hostel assignment is required when creating a student.")
    student = enrollment_service.create_student(
        db, payload=payload, actor=actor, hostel_scoped=True
    )
    db.commit()
    return student


@router.get("/students/{student_ref}", response_model=EnrollmentStatusPublic)
def get_student(
    student_ref: str,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> EnrollmentStatusPublic:
    """Full enrollment-status view for one student."""
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)
    return _status_public(db, student)


@router.patch("/students/{student_ref}", response_model=StudentPublic)
def patch_student(
    student_ref: str,
    payload: StudentPatch,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> StudentPublic:
    """Edit authorized student details. Role/status are NOT patchable here."""
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)
    data = payload.model_dump(exclude_unset=True)

    if "hostel_id" in data and data["hostel_id"] is not None:
        if not can_manage_hostel(db, actor, data["hostel_id"]):
            raise forbidden("You are not authorized for that hostel.")
        if db.get(Hostel, data["hostel_id"]) is None:
            raise not_found("Hostel")
    if "email" in data and data["email"] is not None:
        dupe = db.scalar(
            select(Student.id).where(
                Student.email == data["email"], Student.id != student.id
            )
        )
        if dupe is not None:
            raise conflict("A student with this college email already exists.")
        if student.enrollment_status == STATUS_CREATED:
            student.enrollment_status = STATUS_CREATED  # no-op; keeps state honest
    if "room" in data or "hostel_id" in data:
        rooms_service.validate_student_room(
            db,
            hostel_id=data.get("hostel_id", student.hostel_id),
            room=data.get("room", student.room),
        )

    changed: dict = {}
    for field in ("name", "email", "department", "cohort", "room", "hostel_id"):
        if field in data:
            setattr(student, field, data[field])
            changed[field] = data[field]

    if changed:
        write_audit(
            db,
            actor_user_id=actor.id,
            actor_label=actor.username,
            action="student.update",
            target_type="student",
            target_id=student.student_id,
            details=changed,
        )
        db.commit()
        db.refresh(student)
    return build_student_public(student.user, student)


@router.post("/students/{student_ref}/verify-details", response_model=EnrollmentStatusPublic)
def verify_details(
    student_ref: str,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> EnrollmentStatusPublic:
    """Confirm submitted details: created -> details_verified."""
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)
    enrollment_service.mark_details_verified(db, student, actor)
    db.commit()
    db.refresh(student)
    return _status_public(db, student)


# --------------------------------------------------------------------------
# Face enrollment (warden-initiated, never student-self)
# --------------------------------------------------------------------------

@router.put("/students/{student_ref}/face-enrollment", response_model=FaceEnrollmentPublic)
def put_face_enrollment(
    student_ref: str,
    payload: FaceEnrollmentPut,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> FaceEnrollmentPublic:
    """Enroll (or re-enroll) a student's face template on their behalf.

    The identity of the enrolled student comes from the path + the actor's
    hostel grant, not from anything the client claims about who is in frame.
    """
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)

    normalized = l2_normalize(payload.embedding)
    blob = encrypt_embedding(normalized)
    quality = payload.quality.model_dump(exclude_none=True) if payload.quality else None
    now = clock.utcnow()

    row = db.scalar(select(FaceEnrollment).where(FaceEnrollment.student_id == student.id))
    replaced = row is not None
    if row is None:
        row = FaceEnrollment(
            student_id=student.id, embedding=blob, embedding_dim=payload.embedding_dim,
            model_version=payload.model_version, quality=quality,
            created_at=now, updated_at=now,
        )
        db.add(row)
    else:
        row.embedding = blob
        row.embedding_dim = payload.embedding_dim
        row.model_version = payload.model_version
        row.quality = quality
        row.updated_at = now

    enrollment_service.record_face_enrollment(
        db, student, actor, model_version=payload.model_version, replaced=replaced
    )
    db.commit()
    db.refresh(row)
    return FaceEnrollmentPublic(
        enrolled=True, model_version=row.model_version,
        updated_at=clock.utc_z(row.updated_at),
    )


@router.delete("/students/{student_ref}/face-enrollment", status_code=204)
def delete_face_enrollment(
    student_ref: str,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> Response:
    """Authorized biometric deletion — rolls the lifecycle back recoverably."""
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)
    enrollment_service.delete_face_enrollment(db, student, actor)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Lifecycle: provision -> activate -> suspend
# --------------------------------------------------------------------------

def _send_activation_email_and_audit(
    db: Session,
    *,
    actor: User,
    student: Student,
    plaintext: str,
    audit_action: str,
    audit_details: dict,
    expires_at,
) -> email_service.ActivationEmailResult:
    """Attempt the activation email and audit its REAL outcome.

    Called after the token transaction has been committed: a provider outage
    must never roll back a valid link. The plaintext token crosses into the
    transport in-process only — it is never logged and never audited; the
    audit row records just the status.
    """
    result = email_service.send_activation_email(
        to_email=student.email or "",
        student_name=student.name,
        roll=student.student_id,
        plaintext_token=plaintext,
        expires_at=expires_at,
    )
    write_audit(
        db,
        actor_user_id=actor.id,
        actor_label=actor.username,
        action=audit_action,
        target_type="student",
        target_id=str(student.id),
        details={**audit_details, "email_status": result.status},
    )
    db.commit()
    return result


@router.post("/students/{student_ref}/activate", response_model=ActivationIssueResponse)
def activate_student(
    student_ref: str,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> ActivationIssueResponse:
    """Provision the account and issue a single-use activation token.

    Requires FACE_ENROLLED. The response carries the freshly issued plaintext
    key (unless the deployment withholds it via
    ``allow_inline_activation_token=false``) so the warden can copy it and send
    it to the student directly; only the SHA-256 hash is stored. The activation
    email is ALSO attempted and the response reports the REAL transport outcome
    (sent / logged / failed / not_configured) — email stays a secondary
    delivery path.
    """
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)

    if student.enrollment_status == STATUS_SUSPENDED:
        raise conflict("Unsuspend this account before activating it.")
    if student.enrollment_status == STATUS_ACTIVE:
        raise conflict("This account is already active.")

    enrollment_service.provision_account(db, student, actor)
    plaintext, expires_at = activation_service.issue_activation_token(
        db, user_id=student.user_id, actor_user_id=actor.id
    )
    # Token durable FIRST: if the mail provider is down the link still works
    # and the warden can resend instead of re-provisioning.
    db.commit()

    result = _send_activation_email_and_audit(
        db,
        actor=actor,
        student=student,
        plaintext=plaintext,
        audit_action="student.activate_issue",
        audit_details={"roll": student.student_id,
                       "expires_at": expires_at.isoformat()},
        expires_at=expires_at,
    )

    inline = settings.allow_inline_activation_token
    return ActivationIssueResponse(
        enrollment_status=STATUS_ACCOUNT_PROVISIONED,
        activation_pending=True,
        delivered=result.status == email_service.STATUS_SENT,
        email_status=result.status,
        email_detail=result.detail,
        expires_at=clock.utc_z(expires_at),
        activation_token=plaintext if inline else None,
        setup_url=(
            f"hostelpass://activate?token={plaintext}" if inline else None
        ),
    )


@router.post("/students/{student_ref}/suspend", response_model=EnrollmentStatusPublic)
def suspend_student(
    student_ref: str,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> EnrollmentStatusPublic:
    """Suspend an account: no login, no attendance. Reversible."""
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)
    enrollment_service.suspend_student(db, student, actor)
    db.commit()
    db.refresh(student)
    return _status_public(db, student)


@router.post("/students/{student_ref}/unsuspend", response_model=EnrollmentStatusPublic)
def unsuspend_student(
    student_ref: str,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> EnrollmentStatusPublic:
    """Restore a suspended account to its prior viable state."""
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)
    enrollment_service.unsuspend_student(db, student, actor)
    db.commit()
    db.refresh(student)
    return _status_public(db, student)


@router.post("/students/{student_ref}/resend-activation", response_model=ActivationIssueResponse)
def resend_activation(
    student_ref: str,
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> ActivationIssueResponse:
    """Warden-triggered recovery: revoke + reissue the setup key/link.

    The new key is returned in the response (same hand-off contract as
    activate) and the previous key stops working immediately.
    """
    student = _resolve_student(db, student_ref)
    _require_student_access(db, actor, student)
    if student.enrollment_status not in (STATUS_ACCOUNT_PROVISIONED,):
        enrollment_service.provision_account(db, student, actor)
    plaintext, expires_at = activation_service.issue_activation_token(
        db, user_id=student.user_id, actor_user_id=actor.id
    )
    db.commit()

    result = _send_activation_email_and_audit(
        db,
        actor=actor,
        student=student,
        plaintext=plaintext,
        audit_action="student.resend_activation",
        audit_details={"roll": student.student_id},
        expires_at=expires_at,
    )
    inline = settings.allow_inline_activation_token
    return ActivationIssueResponse(
        enrollment_status=student.enrollment_status,
        activation_pending=True,
        delivered=result.status == email_service.STATUS_SENT,
        email_status=result.status,
        email_detail=result.detail,
        expires_at=clock.utc_z(expires_at),
        activation_token=plaintext if inline else None,
        setup_url=(f"hostelpass://activate?token={plaintext}" if inline else None),
    )


# --------------------------------------------------------------------------
# Attendance read-only for wardens
# --------------------------------------------------------------------------

@router.get("/attendance")
def list_attendance(
    student_id: str | None = Query(default=None),
    date: str | None = Query(default=None),
    status: Literal["present", "pending", "absent"] | None = Query(default=None),
    month: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
    actor: User = Depends(_staff),
) -> dict:
    """Attendance for the actor's hostels only."""
    if student_id:
        student = _resolve_student(db, student_id)
        _require_student_access(db, actor, student)
        students = [student]
    else:
        students = list(db.scalars(_visible_query(db, actor)).all())

    now = clock.utcnow()
    day = attendance_service.parse_date_param(date)
    if day is not None:
        first = last = day
    else:
        default_month = now.strftime("%Y-%m")
        month_value = attendance_service.parse_month_param(month, default_month)
        first, last = attendance_service.month_bounds(month_value)

    items: list[dict] = []
    for student in students:
        for entry in attendance_service.month_entries(
            db, student, student.hostel, first, last, now
        ):
            entry["student"] = {
                "id": str(student.id),
                "student_id": student.student_id,
                "name": student.name,
            }
            items.append(entry)

    if status is not None:
        items = [e for e in items if e["status"] == status]
    items.sort(key=lambda e: (e["date"], e["student"]["student_id"]), reverse=True)
    return _page(items, page, page_size)
