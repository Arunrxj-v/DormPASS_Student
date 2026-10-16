"""Admin/warden schemas."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .attendance import AttendancePublic
from .auth import StudentPublic

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class StudentCreate(BaseModel):
    """POST /admin/students and POST /warden/students body.

    No password is ever supplied by staff: the student establishes their own
    password by redeeming a single-use activation token (section 7).
    ``email`` is required and must be a real @ceconline.edu address —
    validated exactly (not substring) on both client and server.
    """

    student_id: str = Field(min_length=3, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=5, max_length=254)
    department: str | None = Field(default=None, max_length=128)
    cohort: str | None = Field(default=None, max_length=64)
    room: str | None = Field(default=None, max_length=32)
    hostel_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _college_domain(cls, value: str) -> str:
        from ..services.identity import EmailValidationError, validate_college_email

        try:
            return validate_college_email(value)
        except EmailValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("student_id")
    @classmethod
    def _roll_shape(cls, value: str) -> str:
        import re

        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_/.]{2,31}", value):
            raise ValueError(
                "student_id may contain letters, digits, '-', '_', '/', '.' (3-32 chars)"
            )
        return value


class StudentPatch(BaseModel):
    """PATCH /warden/students/{id} body — all fields optional.

    Role, enrollment_status and account_status are NOT patchable here; those
    change only through the dedicated lifecycle endpoints.
    """

    name: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=254)
    department: str | None = Field(default=None, max_length=128)
    cohort: str | None = Field(default=None, max_length=64)
    room: str | None = Field(default=None, max_length=32)
    hostel_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _college_domain(cls, value: str | None) -> str | None:
        if value is None:
            return value
        from ..services.identity import EmailValidationError, validate_college_email

        try:
            return validate_college_email(value)
        except EmailValidationError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("hostel_id", mode="before")
    @classmethod
    def _hostel_id_or_null(cls, value):
        # Allows {"hostel_id": null} to explicitly unassign a hostel.
        return value


# --------------------------------------------------------------------------
# Warden workflow schemas
# --------------------------------------------------------------------------

class WardenStudentCreate(StudentCreate):
    """POST /warden/students body (same shape as StudentCreate)."""


class WardenStudentFilter(BaseModel):
    """GET /warden/students query model (all optional)."""

    q: str | None = Field(default=None, max_length=128)
    hostel_id: UUID | None = None
    room: str | None = Field(default=None, max_length=32)
    enrollment_status: str | None = None


class EnrollmentStatusPublic(BaseModel):
    """GET /warden/students/{id} — truthful lifecycle state from the DB."""

    student_id: UUID
    roll: str
    name: str
    email: str | None
    enrollment_status: str
    account_status: str
    details_complete: bool
    face_enrolled: bool
    password_set: bool
    activation_pending: bool
    hostel_id: UUID | None = None
    room: str | None = None


class ActivationIssueResponse(BaseModel):
    """POST /warden/students/{id}/activate — provisioning step.

    ``activation_token`` is the freshly issued single-use key, returned at the
    issuance moment so the issuing warden can copy it and hand it to the
    student (WhatsApp workflow). Only its hash is stored server-side; the key
    is never echoed by any read endpoint or written to logs. Deployments that
    prefer email-only delivery can withhold it with
    ``allow_inline_activation_token=false`` (the field is then ``null``).

    ``email_status`` is the REAL delivery outcome for the activation email:
      * ``sent``             — an SMTP provider accepted the message.
      * ``logged``           — development EMAIL_MODE=log: rendered to the
                               server's local outbox, no real email sent.
      * ``failed``           — delivery attempted but failed (``email_detail``
                               carries a token-free reason).
      * ``not_configured``   — EMAIL_MODE=off: no delivery was attempted.
    ``delivered`` is true ONLY when ``email_status == "sent"`` — creating an
    activation record never claims a send on its own.
    """

    enrollment_status: str
    activation_pending: bool
    delivered: bool
    email_status: Literal["sent", "logged", "failed", "not_configured"]
    email_detail: str | None = None
    expires_at: str | None = None  # RFC 3339 UTC
    activation_token: str | None = None
    setup_url: str | None = None


class WardenDashboard(BaseModel):
    """GET /warden/dashboard."""

    total_students: int
    active_students: int
    pending_enrollment: int
    face_enrolled: int
    suspended_students: int
    hostels: list[dict]
    recent_activity: list[dict]
    attendance_today: dict


class HostelUpdate(BaseModel):
    """PUT /admin/hostels/{id} body — geofence & policy config (optional fields;
    PUT acts as a targeted config update so clients don't round-trip everything)."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    block: str | None = Field(default=None, max_length=32)
    anchor_label: str | None = Field(default=None, max_length=128)
    latitude: float | None = None
    longitude: float | None = None
    permitted_radius_m: float | None = Field(default=None, gt=0, le=100_000)
    max_location_accuracy_m: float | None = Field(default=None, gt=0, le=10_000)
    boundary_policy: Literal["conservative"] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    window_start: str | None = None
    window_end: str | None = None
    require_liveness: bool | None = None
    face_match_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    warden_name: str | None = Field(default=None, max_length=128)
    warden_extension: str | None = Field(default=None, max_length=16)

    @field_validator("window_start", "window_end")
    @classmethod
    def _hhmm(cls, value: str | None) -> str | None:
        if value is not None and not _HHMM.match(value):
            raise ValueError("window time must be HH:MM (24h)")
        return value

    @field_validator("latitude")
    @classmethod
    def _lat(cls, value: float | None) -> float | None:
        if value is not None and not -90.0 <= value <= 90.0:
            raise ValueError("latitude must be between -90 and 90")
        return value

    @field_validator("longitude")
    @classmethod
    def _lon(cls, value: float | None) -> float | None:
        if value is not None and not -180.0 <= value <= 180.0:
            raise ValueError("longitude must be between -180 and 180")
        return value

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        if value is not None:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"unknown timezone: {value}") from exc
        return value


class HostelCreate(HostelUpdate):
    """POST /admin/hostels body — create a hostel block.

    Geofence inputs are MANDATORY: a hostel without a usable anchor would
    silently deny attendance for every student in it, so the API refuses to
    create one. Defaults (window, timezone, liveness, threshold) match the
    deployment's existing policy.
    """

    name: str = Field(min_length=1, max_length=128)
    latitude: float
    longitude: float
    permitted_radius_m: float = Field(gt=0, le=100_000)
    max_location_accuracy_m: float = Field(gt=0, le=10_000)


class RoomCreate(BaseModel):
    """POST /admin/hostels/{id}/rooms body."""

    identifier: str = Field(min_length=1, max_length=32)
    capacity: int | None = Field(default=None, ge=1, le=1000)

    @field_validator("identifier")
    @classmethod
    def _shape(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("room identifier must not be blank")
        return value


class RoomPatch(BaseModel):
    """PATCH /admin/rooms/{id} body — identifier and/or capacity."""

    identifier: str | None = Field(default=None, min_length=1, max_length=32)
    capacity: int | None = Field(default=None, ge=1, le=1000)

    @field_validator("identifier")
    @classmethod
    def _shape(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("room identifier must not be blank")
        return value


class RoomPublic(BaseModel):
    """GET /admin/hostels/{id}/rooms item — registry row + live occupancy."""

    id: UUID
    hostel_id: UUID
    identifier: str
    capacity: int | None = None
    student_count: int = 0
    created_at: str | None = None  # RFC 3339 UTC
    updated_at: str | None = None  # RFC 3339 UTC


class CorrectionRequest(BaseModel):
    """POST /admin/attendance/{id}/correction body."""

    new_status: Literal["present", "pending", "absent"]
    reason: str = Field(min_length=3, max_length=500)


class WardenCreate(BaseModel):
    """POST /admin/wardens body — admin-controlled staff provisioning.

    Wardens are never self-registered; an administrator creates them and
    assigns the hostels they may manage.
    """

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=128)
    hostel_ids: list[UUID] = Field(default_factory=list, max_length=50)

    @field_validator("username")
    @classmethod
    def _username_shape(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ch.isspace() for ch in value):
            raise ValueError("username must not contain whitespace")
        return value


class WardenPatch(BaseModel):
    """PATCH /admin/wardens/{username} body."""

    password: str | None = Field(default=None, min_length=10, max_length=128)
    hostel_ids: list[UUID] | None = Field(default=None, max_length=50)
    account_status: Literal["active", "inactive"] | None = None


class WardenPublic(BaseModel):
    """GET /admin/wardens item."""

    id: UUID
    username: str
    role: str
    account_status: str
    hostel_ids: list[UUID] = Field(default_factory=list)
    hostel_names: list[str] = Field(default_factory=list)
    created_at: str | None = None  # RFC 3339 UTC


class AdminStudentRef(BaseModel):
    """Student identity attached to admin attendance list items."""

    id: UUID
    student_id: str
    name: str


class AdminAttendanceItem(AttendancePublic):
    """AttendancePublic + owning student (extra field; additive for clients)."""

    student: AdminStudentRef | None = None


class AuditLogPublic(BaseModel):
    """GET /admin/audit-logs item."""

    id: UUID
    actor: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    details: dict | None = None
    created_at: str  # RFC 3339 UTC


class PageEnvelope(BaseModel):
    """Pagination metadata shared by admin list endpoints."""

    page: int
    page_size: int
    total_pages: int
    has_more: bool


class StudentListResponse(PageEnvelope):
    items: list[StudentPublic]


class WardenListResponse(PageEnvelope):
    items: list[WardenPublic]


class AttendanceListResponse(PageEnvelope):
    items: list[AdminAttendanceItem]


class RoomListResponse(PageEnvelope):
    items: list[RoomPublic]


class AuditLogListResponse(PageEnvelope):
    items: list[AuditLogPublic]
