"""Admin/warden endpoints (role-gated): students, hostels, attendance
workflow, biometric deletion, audit logs. Every mutation writes audit_logs."""

from __future__ import annotations

import math
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete as sa_delete
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core import clock
from ..core.errors import conflict, not_found
from ..core.roles import STATUS_ACTIVE, STATUS_SUSPENDED
from ..core.security import hash_password
from ..db.session import get_session
from ..models import (
    AuditLog,
    AttendanceRecord,
    FaceEnrollment,
    Hostel,
    Room,
    Student,
    User,
    WardenHostel,
)
from ..schemas import (
    AdminAttendanceItem,
    AttendanceListResponse,
    AuditLogListResponse,
    AuditLogPublic,
    CorrectionRequest,
    GeofencePublic,
    HostelCreate,
    HostelUpdate,
    RoomCreate,
    RoomListResponse,
    RoomPatch,
    RoomPublic,
    StudentCreate,
    StudentListResponse,
    StudentPatch,
    StudentPublic,
    WardenCreate,
    WardenListResponse,
    WardenPatch,
    WardenPublic,
)
from ..services import attendance as attendance_service
from ..services import enrollment as enrollment_service
from ..services import rooms as rooms_service
from ..services.audit import write_audit
from ..services.students import build_student_public
from .deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _page(items: list, page: int, page_size: int) -> dict:
    """Shared pagination envelope (matches history: total_pages 0 when empty)."""
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


def _resolve_student(db: Session, ref: str) -> Student:
    """Accept either a student UUID or the roll number as {id}."""
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


def _resolve_hostel(db: Session, ref: str) -> Hostel:
    try:
        row = db.get(Hostel, UUID(ref))
    except ValueError:
        row = None
    if row is None:
        raise not_found("Hostel")
    return row


def _admin_item(db: Session, record: AttendanceRecord, student: Student | None = None) -> dict:
    """AttendancePublic + owning student for admin list/workflow responses."""
    if student is None:
        student = db.get(Student, record.student_id)
    if student is None:
        raise not_found("Student")
    return {
        **attendance_service.record_to_public(record, student.hostel),
        "student": {"id": student.id, "student_id": student.student_id, "name": student.name},
    }


def _record_ref(record: AttendanceRecord) -> dict:
    return {"reference": record.reference, "date": record.attendance_date.isoformat()}


# --------------------------------------------------------------------------
# Students
# --------------------------------------------------------------------------

@router.get("/students", response_model=StudentListResponse)
def list_students(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=128,
                          description="roll / name / email substring"),
    hostel_id: UUID | None = Query(default=None),
    enrollment_status: str | None = Query(default=None),
    account_status: str | None = Query(default=None),
    db: Session = Depends(get_session),
) -> StudentListResponse:
    """Paginated student roster, optionally filtered (admin console overview)."""
    stmt = select(Student)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            Student.student_id.ilike(like)
            | Student.name.ilike(like)
            | Student.email.ilike(like)
        )
    if hostel_id is not None:
        stmt = stmt.where(Student.hostel_id == hostel_id)
    if enrollment_status:
        stmt = stmt.where(Student.enrollment_status == enrollment_status)
    if account_status:
        stmt = stmt.where(Student.user.has(User.account_status == account_status))

    rows = db.scalars(stmt.order_by(Student.student_id)).all()
    items = [build_student_public(s.user, s) for s in rows]
    return _page(items, page, page_size)


@router.post("/students", response_model=StudentPublic, status_code=201)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> StudentPublic:
    """Create a student record + login identity (no staff-chosen password).

    The account starts INACTIVE at ``created``; the student sets their own
    password by redeeming a warden-issued activation token.
    """
    student = enrollment_service.create_student(db, payload=payload, actor=admin)
    db.commit()
    return student


@router.patch("/students/{student_ref}", response_model=StudentPublic)
def patch_student(
    student_ref: str,
    payload: StudentPatch,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> StudentPublic:
    """Partial update of a student (details / hostel reassignment)."""
    student = _resolve_student(db, student_ref)
    data = payload.model_dump(exclude_unset=True)

    if "hostel_id" in data and data["hostel_id"] is not None:
        if db.get(Hostel, data["hostel_id"]) is None:
            raise not_found("Hostel")
    if "email" in data and data["email"] is not None:
        dupe = db.scalar(
            select(Student.id).where(Student.email == data["email"], Student.id != student.id)
        )
        if dupe is not None:
            raise conflict("A student with this college email already exists.")
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
            changed[field] = str(data[field]) if data[field] is not None else None
    if changed:
        write_audit(
            db,
            actor_user_id=admin.id,
            actor_label=admin.username,
            action="student.update",
            target_type="student",
            target_id=student.student_id,
            details=changed,
        )
        db.commit()
        db.refresh(student)
    return build_student_public(student.user, student)


@router.post("/students/{student_ref}/suspend", response_model=StudentPublic)
def suspend_student(
    student_ref: str,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> StudentPublic:
    """Suspend a student account (blocks login and attendance)."""
    student = _resolve_student(db, student_ref)
    enrollment_service.suspend_student(db, student, admin)
    db.commit()
    db.refresh(student)
    return build_student_public(student.user, student)


@router.post("/students/{student_ref}/unsuspend", response_model=StudentPublic)
def unsuspend_student(
    student_ref: str,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> StudentPublic:
    """Reverse a suspension, restoring the prior viable state."""
    student = _resolve_student(db, student_ref)
    enrollment_service.unsuspend_student(db, student, admin)
    db.commit()
    db.refresh(student)
    return build_student_public(student.user, student)


@router.delete("/students/{student_ref}/face-enrollment", status_code=204)
def admin_delete_face_enrollment(
    student_ref: str,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> Response:
    """Audit-logged biometric deletion for a student (recoverable rollback)."""
    student = _resolve_student(db, student_ref)
    enrollment_service.delete_face_enrollment(db, student, admin)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Staff accounts (admin-controlled; never self-registered)
# --------------------------------------------------------------------------

def _warden_public(db: Session, user: User) -> dict:
    rows = db.execute(
        select(WardenHostel.hostel_id, Hostel.name)
        .join(Hostel, Hostel.id == WardenHostel.hostel_id)
        .where(WardenHostel.user_id == user.id)
    ).all()
    return WardenPublic(
        id=user.id,
        username=user.username,
        role=user.role,
        account_status=user.account_status,
        hostel_ids=[r[0] for r in rows],
        hostel_names=[r[1] for r in rows],
        created_at=clock.utc_z(user.created_at),
    )


@router.get("/wardens", response_model=WardenListResponse)
def list_wardens(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=128, description="username substring"),
    account_status: str | None = Query(default=None),
    db: Session = Depends(get_session),
) -> WardenListResponse:
    """All warden accounts with their hostel grants (optionally filtered)."""
    stmt = select(User).where(User.role == "warden")
    if q:
        stmt = stmt.where(User.username.ilike(f"%{q.strip()}%"))
    if account_status:
        stmt = stmt.where(User.account_status == account_status)
    rows = db.scalars(stmt.order_by(User.username)).all()
    items = [_warden_public(db, u) for u in rows]
    return _page(items, page, page_size)


@router.post("/wardens", response_model=WardenPublic, status_code=201)
def create_warden(
    payload: WardenCreate,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WardenPublic:
    """Create a warden account and grant it the listed hostels."""
    if db.scalar(select(User.id).where(func.lower(User.username) == payload.username.lower())):
        raise conflict("That username is already taken.")
    for hostel_id in payload.hostel_ids:
        if db.get(Hostel, hostel_id) is None:
            raise not_found("Hostel")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="warden",
        account_status="active",
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("That username is already taken.") from exc

    for hostel_id in dict.fromkeys(payload.hostel_ids):
        db.add(WardenHostel(user_id=user.id, hostel_id=hostel_id))

    write_audit(
        db,
        actor_user_id=admin.id,
        actor_label=admin.username,
        action="warden.create",
        target_type="user",
        target_id=str(user.id),
        details={"username": payload.username,
                 "hostels": [str(h) for h in payload.hostel_ids]},
    )
    db.commit()
    db.refresh(user)
    return _warden_public(db, user)


@router.patch("/wardens/{username}", response_model=WardenPublic)
def patch_warden(
    username: str,
    payload: WardenPatch,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> WardenPublic:
    """Update a warden's password, hostel grants, or account status."""
    user = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if user is None or user.role != "warden":
        raise not_found("Warden")
    if user.id == admin.id:
        raise conflict("Use a separate account to modify an administrator.")

    data = payload.model_dump(exclude_unset=True)
    changed: dict = {}

    if "password" in data and data["password"]:
        user.password_hash = hash_password(data["password"])
        changed["password"] = "reset"
    if "account_status" in data and data["account_status"]:
        user.account_status = data["account_status"]
        changed["account_status"] = data["account_status"]
    if "hostel_ids" in data and data["hostel_ids"] is not None:
        for hostel_id in data["hostel_ids"]:
            if db.get(Hostel, hostel_id) is None:
                raise not_found("Hostel")
        db.execute(sa_delete(WardenHostel).where(WardenHostel.user_id == user.id))
        for hostel_id in dict.fromkeys(data["hostel_ids"]):
            db.add(WardenHostel(user_id=user.id, hostel_id=hostel_id))
        changed["hostels"] = [str(h) for h in data["hostel_ids"]]

    if changed:
        write_audit(
            db,
            actor_user_id=admin.id,
            actor_label=admin.username,
            action="warden.update",
            target_type="user",
            target_id=str(user.id),
            details={"username": user.username, **changed},
        )
        db.commit()
        db.refresh(user)
    return _warden_public(db, user)


@router.delete("/wardens/{username}", status_code=204)
def delete_warden(
    username: str,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> Response:
    """Deactivate + remove a warden (audit-logged)."""
    user = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if user is None or user.role != "warden":
        raise not_found("Warden")
    if user.id == admin.id:
        raise conflict("Cannot remove the administrator account this way.")
    write_audit(
        db,
        actor_user_id=admin.id,
        actor_label=admin.username,
        action="warden.delete",
        target_type="user",
        target_id=str(user.id),
        details={"username": user.username},
    )
    db.delete(user)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Hostels
# --------------------------------------------------------------------------

@router.get("/hostels", response_model=list[GeofencePublic])
def list_hostels(db: Session = Depends(get_session)) -> list[GeofencePublic]:
    """All hostel geofence configs."""
    rows = db.scalars(select(Hostel).order_by(Hostel.name)).all()
    return [GeofencePublic.from_hostel(h) for h in rows]


@router.get("/hostels/{hostel_id}", response_model=GeofencePublic)
def get_hostel(
    hostel_id: str,
    db: Session = Depends(get_session),
) -> GeofencePublic:
    """One hostel's geofence & attendance policy (admin console detail view)."""
    return GeofencePublic.from_hostel(_resolve_hostel(db, hostel_id))


@router.post("/hostels", response_model=GeofencePublic, status_code=201)
def create_hostel(
    payload: HostelCreate,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> GeofencePublic:
    """Create a hostel block with its geofence & attendance policy (audited).

    The client cannot invent coordinates: latitude/longitude/radius/accuracy
    are required so the server always has a usable anchor to enforce.
    """
    name = payload.name.strip()
    block = payload.block.strip() if payload.block else None
    dupe = db.scalar(
        select(Hostel).where(
            func.lower(Hostel.name) == name.lower(),
            Hostel.block.is_(None) if block is None else func.lower(Hostel.block) == block.lower(),
        )
    )
    if dupe is not None:
        raise conflict("A hostel with this name and block already exists.")

    data = payload.model_dump(exclude={"name", "block"})
    hostel = Hostel(name=name, block=block, **data)
    db.add(hostel)
    try:
        db.flush()
        write_audit(
            db,
            actor_user_id=admin.id,
            actor_label=admin.username,
            action="hostel.create",
            target_type="hostel",
            target_id=str(hostel.id),
            details={"name": name, "block": block,
                     "latitude": data["latitude"], "longitude": data["longitude"],
                     "permitted_radius_m": data["permitted_radius_m"]},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("A hostel with this name and block already exists.") from exc
    db.refresh(hostel)
    return GeofencePublic.from_hostel(hostel)


@router.put("/hostels/{hostel_id}", response_model=GeofencePublic)
def update_hostel(
    hostel_id: str,
    payload: HostelUpdate,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> GeofencePublic:
    """Update geofence & attendance policy (audit-logged).

    Only fields present in the body are changed; the server validates ranges
    and timezone names. This config is what every verify enforces.
    """
    hostel = _resolve_hostel(db, hostel_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(hostel, field, value)
    try:
        write_audit(
            db,
            actor_user_id=admin.id,
            actor_label=admin.username,
            action="hostel.update",
            target_type="hostel",
            target_id=str(hostel.id),
            details={k: (str(v) if not isinstance(v, (int, float, bool, type(None))) else v)
                     for k, v in data.items()},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("A hostel with this name and block already exists.") from exc
    db.refresh(hostel)
    return GeofencePublic.from_hostel(hostel)


# --------------------------------------------------------------------------
# Rooms (registry per hostel; students.room stays a plain string)
# --------------------------------------------------------------------------

def _resolve_room(db: Session, ref: str) -> Room:
    try:
        row = db.get(Room, UUID(ref))
    except ValueError:
        row = None
    if row is None:
        raise not_found("Room")
    return row


def _room_public(db: Session, room: Room) -> dict:
    """RoomPublic + live occupancy (students whose room string matches)."""
    return RoomPublic(
        id=room.id,
        hostel_id=room.hostel_id,
        identifier=room.identifier,
        capacity=room.capacity,
        student_count=rooms_service.occupied_count(
            db, hostel_id=room.hostel_id, identifier=room.identifier
        ),
        created_at=clock.utc_z(room.created_at),
        updated_at=clock.utc_z(room.updated_at),
    )


@router.get("/hostels/{hostel_id}/rooms", response_model=RoomListResponse)
def list_rooms(
    hostel_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=200),
    db: Session = Depends(get_session),
) -> RoomListResponse:
    """Rooms registered for one hostel, with live occupancy counts."""
    hostel = _resolve_hostel(db, hostel_id)
    rows = db.scalars(
        select(Room).where(Room.hostel_id == hostel.id).order_by(Room.identifier)
    ).all()
    items = [_room_public(db, r) for r in rows]
    return _page(items, page, page_size)


@router.post("/hostels/{hostel_id}/rooms", response_model=RoomPublic, status_code=201)
def create_room(
    hostel_id: str,
    payload: RoomCreate,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> RoomPublic:
    """Register a room in a hostel (audit-logged)."""
    hostel = _resolve_hostel(db, hostel_id)
    identifier = payload.identifier.strip()
    dupe = db.scalar(
        select(Room.id).where(
            Room.hostel_id == hostel.id,
            func.lower(Room.identifier) == identifier.lower(),
        )
    )
    if dupe is not None:
        raise conflict(f"Room {identifier} already exists in this hostel.")

    room = Room(hostel_id=hostel.id, identifier=identifier, capacity=payload.capacity)
    db.add(room)
    try:
        db.flush()
        write_audit(
            db,
            actor_user_id=admin.id,
            actor_label=admin.username,
            action="room.create",
            target_type="room",
            target_id=str(room.id),
            details={"hostel_id": str(hostel.id), "identifier": identifier,
                     "capacity": payload.capacity},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict(f"Room {identifier} already exists in this hostel.") from exc
    db.refresh(room)
    return _room_public(db, room)


@router.patch("/rooms/{room_id}", response_model=RoomPublic)
def update_room(
    room_id: UUID,
    payload: RoomPatch,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> RoomPublic:
    """Rename a room or change its advisory capacity (audit-logged).

    Renaming is allowed while students occupy the room — their free-text
    ``students.room`` string is updated in the same transaction so nobody is
    silently orphaned by the rename.
    """
    room = db.get(Room, room_id)
    if room is None:
        raise not_found("Room")
    data = payload.model_dump(exclude_unset=True)
    changed: dict = {}

    if "identifier" in data and data["identifier"] is not None:
        identifier = data["identifier"].strip()
        dupe = db.scalar(
            select(Room.id).where(
                Room.hostel_id == room.hostel_id,
                func.lower(Room.identifier) == identifier.lower(),
                Room.id != room.id,
            )
        )
        if dupe is not None:
            raise conflict(f"Room {identifier} already exists in this hostel.")
        old = room.identifier
        if old != identifier:
            # Keep occupants attached to the renamed room.
            moved = db.scalars(
                select(Student).where(
                    Student.hostel_id == room.hostel_id,
                    func.lower(func.coalesce(Student.room, "")) == old.lower(),
                )
            ).all()
            for student in moved:
                student.room = identifier
            room.identifier = identifier
            changed["identifier"] = {"from": old, "to": identifier, "students_moved": len(moved)}

    if "capacity" in data:
        room.capacity = data["capacity"]
        changed["capacity"] = data["capacity"]

    if changed:
        write_audit(
            db,
            actor_user_id=admin.id,
            actor_label=admin.username,
            action="room.update",
            target_type="room",
            target_id=str(room.id),
            details={"hostel_id": str(room.hostel_id), **changed},
        )
        db.commit()
        db.refresh(room)
    return _room_public(db, room)


@router.delete("/rooms/{room_id}", status_code=204)
def delete_room(
    room_id: UUID,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> Response:
    """Remove an EMPTY room from the registry (audit-logged).

    Refuses (409) while students are still assigned to it, so a delete can
    never orphan a roster entry.
    """
    room = db.get(Room, room_id)
    if room is None:
        raise not_found("Room")
    rooms_service.assert_room_deletable(db, room)
    write_audit(
        db,
        actor_user_id=admin.id,
        actor_label=admin.username,
        action="room.delete",
        target_type="room",
        target_id=str(room.id),
        details={"hostel_id": str(room.hostel_id), "identifier": room.identifier},
    )
    db.delete(room)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Dashboard stats (real counts only — nothing is invented)
# --------------------------------------------------------------------------

@router.get("/stats")
def admin_stats(db: Session = Depends(get_session)) -> dict:
    """Operational counts for the Admin Console dashboard.

    Every figure is a live aggregate over the same tables the rest of the API
    serves; the console never renders a number the backend did not compute.
    """

    def count(stmt) -> int:
        return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)

    hostel_count = count(select(Hostel.id))
    warden_total = count(select(User.id).where(User.role == "warden"))
    warden_active = count(
        select(User.id).where(User.role == "warden", User.account_status == "active")
    )
    student_total = count(select(Student.id))

    status_rows = db.execute(
        select(Student.enrollment_status, func.count()).group_by(Student.enrollment_status)
    ).all()
    by_enrollment = {status: int(n) for status, n in status_rows}

    pending = sum(
        n for status, n in by_enrollment.items()
        if status not in {STATUS_ACTIVE, STATUS_SUSPENDED}
    )

    return {
        "hostels": hostel_count,
        "rooms": count(select(Room.id)),
        "wardens": {"total": warden_total, "active": warden_active,
                    "inactive": warden_total - warden_active},
        "students": {
            "total": student_total,
            "active": by_enrollment.get(STATUS_ACTIVE, 0),
            "pending_enrollment": pending,
            "suspended": by_enrollment.get(STATUS_SUSPENDED, 0),
            "by_status": by_enrollment,
        },
    }


# --------------------------------------------------------------------------
# Attendance workflow
# --------------------------------------------------------------------------

@router.get("/attendance", response_model=AttendanceListResponse)
def list_attendance(
    student_id: str | None = Query(default=None, description="roll number or UUID"),
    date: str | None = Query(default=None, description="YYYY-MM-DD"),
    status: Literal["present", "pending", "absent"] | None = Query(default=None),
    month: str | None = Query(default=None, description="YYYY-MM (when no date)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
) -> AttendanceListResponse:
    """Attendance across students, including synthesized absents/pending."""
    if student_id:
        students = [_resolve_student(db, student_id)]
    else:
        students = list(db.scalars(select(Student).order_by(Student.student_id)).all())

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
        for entry in attendance_service.month_entries(db, student, student.hostel, first, last, now):
            entry["student"] = {
                "id": student.id,
                "student_id": student.student_id,
                "name": student.name,
            }
            items.append(entry)

    if status is not None:
        items = [e for e in items if e["status"] == status]
    items.sort(key=lambda e: (e["date"], e["student"]["student_id"]), reverse=True)
    return _page(items, page, page_size)


@router.post("/attendance/{record_id}/approve", response_model=AdminAttendanceItem)
def approve_attendance(
    record_id: UUID,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> AdminAttendanceItem:
    """Warden approves a pending record -> outcome 'verified'."""
    record = db.get(AttendanceRecord, record_id)
    if record is None:
        raise not_found("Attendance record")
    if record.outcome == "verified":
        raise conflict("Record is already verified.")
    previous = record.outcome
    record.outcome = "verified"
    write_audit(
        db,
        actor_user_id=admin.id,
        actor_label=admin.username,
        action="attendance.approve",
        target_type="attendance_record",
        target_id=str(record.id),
        details={**_record_ref(record), "previous_outcome": previous},
    )
    db.commit()
    db.refresh(record)
    return _admin_item(db, record)


@router.post("/attendance/{record_id}/reject", status_code=204)
def reject_attendance(
    record_id: UUID,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> Response:
    """Warden rejects a claim: the record is removed (day becomes absent)."""
    record = db.get(AttendanceRecord, record_id)
    if record is None:
        raise not_found("Attendance record")
    write_audit(
        db,
        actor_user_id=admin.id,
        actor_label=admin.username,
        action="attendance.reject",
        target_type="attendance_record",
        target_id=str(record.id),
        details={**_record_ref(record), "previous_outcome": record.outcome},
    )
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@router.post("/attendance/{record_id}/correction", response_model=AdminAttendanceItem)
def correct_attendance(
    record_id: UUID,
    payload: CorrectionRequest,
    db: Session = Depends(get_session),
    admin: User = Depends(require_admin),
) -> AdminAttendanceItem:
    """Audit-logged status correction: present <-> pending <-> absent.

    ``absent`` removes the record; that day then synthesizes as absent with
    reason ``curfew_window_missed`` in history/summary.
    """
    record = db.get(AttendanceRecord, record_id)
    if record is None:
        raise not_found("Attendance record")
    previous = record.outcome
    student = db.get(Student, record.student_id)

    write_audit(
        db,
        actor_user_id=admin.id,
        actor_label=admin.username,
        action="attendance.correction",
        target_type="attendance_record",
        target_id=str(record.id),
        details={**_record_ref(record), "new_status": payload.new_status,
                 "previous_outcome": previous, "reason": payload.reason},
    )

    if payload.new_status == "present":
        record.outcome = "verified"
        db.commit()
        db.refresh(record)
        return _admin_item(db, record, student)
    if payload.new_status == "pending":
        record.outcome = "pending_review"
        db.commit()
        db.refresh(record)
        return _admin_item(db, record, student)

    day = record.attendance_date
    db.delete(record)
    db.commit()
    return {
        **attendance_service.absent_entry(day),
        "student": {"id": student.id, "student_id": student.student_id, "name": student.name},
    }


# --------------------------------------------------------------------------
# Audit logs
# --------------------------------------------------------------------------

@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
) -> AuditLogListResponse:
    """Most recent audit entries first."""
    rows = db.scalars(
        select(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id))
    ).all()
    items = [
        AuditLogPublic(
            id=r.id,
            actor=r.actor_label,
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            details=r.details,
            created_at=clock.utc_z(r.created_at),
        )
        for r in rows
    ]
    return _page(items, page, page_size)
