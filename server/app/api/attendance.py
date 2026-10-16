"""Attendance endpoints: status, summary, history, verify."""

from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core import clock
from ..db.session import get_session
from ..models import Student
from ..schemas import (
    AttendancePublic,
    AttendanceStatusResponse,
    HistoryResponse,
    SummaryResponse,
    VerifyRequest,
)
from ..services import attendance as attendance_service
from .deps import get_current_student, verify_rate_limit

router = APIRouter(tags=["attendance"])


@router.get("/attendance/status", response_model=AttendanceStatusResponse)
def attendance_status(
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to today (hostel tz)"),
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_session),
) -> AttendanceStatusResponse:
    """Marking state + window + can_mark for one attendance day."""
    day = attendance_service.parse_date_param(date)
    return attendance_service.build_status(db, student, student.hostel, day)


@router.get("/attendance/summary", response_model=SummaryResponse)
def attendance_summary(
    month: str | None = Query(default=None, description="YYYY-MM; defaults to current month"),
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_session),
) -> SummaryResponse:
    """Present/absent/rate/eligibility for a month (outpass always 0 in v1)."""
    hostel = student.hostel
    tz_name = hostel.timezone if hostel else "UTC"
    default_month = clock.utcnow().astimezone(ZoneInfo(tz_name)).strftime("%Y-%m")
    month_value = attendance_service.parse_month_param(month, default_month)
    return attendance_service.build_summary(db, student, hostel, month_value)


@router.get("/attendance/history", response_model=HistoryResponse)
def attendance_history(
    month: str | None = Query(default=None, description="YYYY-MM; defaults to current month"),
    status: Literal["present", "pending", "absent"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_session),
) -> HistoryResponse:
    """Paginated history with synthesized ``absent`` days (reason in payload)."""
    hostel = student.hostel
    tz_name = hostel.timezone if hostel else "UTC"
    default_month = clock.utcnow().astimezone(ZoneInfo(tz_name)).strftime("%Y-%m")
    month_value = attendance_service.parse_month_param(month, default_month)
    return attendance_service.build_history(
        db, student, hostel, month_value, status, page, page_size
    )


@router.post(
    "/attendance/verify",
    response_model=AttendancePublic,
    dependencies=[Depends(verify_rate_limit)],
)
def verify_attendance(
    payload: VerifyRequest,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_session),
) -> AttendancePublic:
    """The authoritative endpoint — server re-derives every decision."""
    record = attendance_service.verify_attendance(db, student, student.hostel, payload)
    return attendance_service.record_to_public(record, student.hostel)
