"""The authoritative attendance service.

Contains:
- curfew window math in the hostel's local timezone (zoneinfo),
- the ``POST /attendance/verify`` enforcement pipeline (contract order),
- status / summary / history builders with synthesized ``absent`` days.

Decision time flows through :func:`app.core.clock.utcnow` so tests can freeze
it; raw coordinates of attempts are never persisted or logged.
"""

from __future__ import annotations

import calendar
import math
import secrets
import string
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core import clock
from ..core.config import settings
from ..core.errors import (
    AppError,
    conflict,
    duplicate_attendance,
    invalid_payload,
)
from ..models import AttendanceAttempt, AttendanceRecord, FaceEnrollment, Hostel, Student
from . import geofence, similarity, template_crypto
from .audit import write_audit

ABSENT_REASON = "curfew_window_missed"
LIVENESS_METHOD = "antispoof_model_v1"
LIVENESS_MAX_SCORE = 0.2

_SUFFIX_ALPHABET = string.ascii_uppercase + string.digits


# --------------------------------------------------------------------------
# Timezone / window helpers
# --------------------------------------------------------------------------

def hostel_tz(hostel: Hostel) -> ZoneInfo:
    """Timezone of a hostel; an unknown zone means it is not usable."""
    try:
        return ZoneInfo(hostel.timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise AppError(403, "hostel_not_configured",
                       "Hostel timezone is not configured correctly.") from exc


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _num(value: Any) -> float | None:
    """Sanitize a value for JSON details (None for NaN/Inf)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def window_state(hostel: Hostel, now: datetime) -> dict[str, Any]:
    """Current window state in the hostel's local timezone.

    Handles windows that span midnight (start > end). ``minutes_remaining`` is
    full minutes until close while open, otherwise 0.
    """
    tz = hostel_tz(hostel)
    local = now.astimezone(tz)
    start = _parse_hhmm(hostel.window_start)
    end = _parse_hhmm(hostel.window_end)
    current = local.time().replace(tzinfo=None)

    if start <= end:
        is_open = start <= current < end
        close = datetime.combine(local.date(), end, tzinfo=tz)
    else:  # window spans midnight, e.g. 22:00 -> 02:00
        if current >= start:
            is_open = True
            close = datetime.combine(local.date() + timedelta(days=1), end, tzinfo=tz)
        elif current < end:
            is_open = True
            close = datetime.combine(local.date(), end, tzinfo=tz)
        else:
            is_open = False
            close = datetime.combine(local.date() + timedelta(days=1), end, tzinfo=tz)

    minutes = 0
    if is_open:
        minutes = max(0, int((close - local).total_seconds() // 60))
    return {
        "open": is_open,
        "opens_at": hostel.window_start,
        "closes_at": hostel.window_end,
        "minutes_remaining": minutes,
        "timezone": hostel.timezone,
    }


def is_window_elapsed(hostel: Hostel, day: date, now: datetime) -> bool:
    """True when the attendance window for ``day`` is fully in the past.

    Today only counts after its window has closed (contract rule for
    synthesizing absent days).
    """
    tz = hostel_tz(hostel)
    local = now.astimezone(tz)
    start = _parse_hhmm(hostel.window_start)
    end = _parse_hhmm(hostel.window_end)
    close_day = day if start <= end else day + timedelta(days=1)
    close = datetime.combine(close_day, end, tzinfo=tz)
    return local >= close


def local_date(hostel: Hostel, now: datetime) -> date:
    """Today's date in the hostel's timezone."""
    return now.astimezone(hostel_tz(hostel)).date()


# --------------------------------------------------------------------------
# Reference generation
# --------------------------------------------------------------------------

def make_reference(local: datetime, suffix: str | None = None) -> str:
    """Build ``HP-<YYYY>-<MMDD>-<HHMM>`` (+ ``-XXXX`` suffix on collision)."""
    base = f"HP-{local:%Y}-{local:%m%d}-{local:%H%M}"
    return base if suffix is None else f"{base}-{suffix}"


def _new_suffix() -> str:
    return "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(4))


def _unique_violation_name(exc: IntegrityError) -> str | None:
    """Name of the unique constraint that fired, if any (psycopg diag)."""
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None)


# --------------------------------------------------------------------------
# Verify pipeline
# --------------------------------------------------------------------------

def verify_attendance(
    db: Session,
    student: Student,
    hostel: Hostel | None,
    payload: Any,  # schemas.VerifyRequest
) -> AttendanceRecord:
    """Run the full contract-ordered verification pipeline.

    Checks, in order: active+configured -> window -> freshness -> accuracy ->
    conservative geofence -> enrollment exists -> embedding dim/finite/cosine ->
    liveness policy -> duplicate-proof insert. Every attempt (accepted or
    rejected) is persisted without raw coordinates.
    """
    now = clock.utcnow()
    acc = payload.location.accuracy_m
    ctx: dict[str, Any] = {"distance_m": None, "accuracy_m": _num(acc)}

    try:
        record = _verify_pipeline(db, student, hostel, payload, now, ctx)
    except AppError as exc:
        db.rollback()
        db.add(AttendanceAttempt(
            student_id=student.id,
            outcome="rejected",
            rejection_code=exc.code,
            distance_m=ctx["distance_m"],
            accuracy_m=ctx["accuracy_m"],
        ))
        db.commit()
        raise

    db.add(AttendanceAttempt(
        student_id=student.id,
        outcome="accepted",
        rejection_code=None,
        distance_m=ctx["distance_m"],
        accuracy_m=ctx["accuracy_m"],
    ))
    write_audit(
        db,
        actor_user_id=student.user_id,
        actor_label=student.student_id,
        action="attendance.verify",
        target_type="attendance_record",
        target_id=str(record.id),
        details={
            "date": record.attendance_date.isoformat(),
            "outcome": record.outcome,
            "reference": record.reference,
        },
    )
    db.commit()
    return record


def _verify_pipeline(
    db: Session,
    student: Student,
    hostel: Hostel | None,
    payload: Any,
    now: datetime,
    ctx: dict[str, Any],
) -> AttendanceRecord:
    # -- Step 1: authenticated, active, hostel with geofence configured -----
    if student.user.account_status != "active":
        raise AppError(403, "account_inactive", "Account is inactive. Contact your warden.")
    if hostel is None or hostel.boundary_policy != geofence.BOUNDARY_POLICY_CONSERVATIVE:
        raise AppError(403, "hostel_not_configured",
                       "Assigned hostel has no geofence configured.")

    # -- Step 2: attendance window open in hostel-local time ----------------
    win = window_state(hostel, now)
    if not win["open"]:
        raise AppError(403, "attendance_window_closed",
                       "Attendance window is closed.", {"window": win})

    # -- Step 3: location freshness <= 90 s ---------------------------------
    ts = payload.location.timestamp_utc.astimezone(timezone.utc)
    age_seconds = (now - ts).total_seconds()
    if abs(age_seconds) > settings.location_max_age_seconds:
        raise AppError(
            422, "location_stale",
            "Location fix is stale. Capture a fresh GPS fix and try again.",
            {"age_seconds": round(age_seconds, 1),
             "max_age_seconds": settings.location_max_age_seconds},
        )

    # -- Step 4: accuracy sane ---------------------------------------------
    acc = payload.location.accuracy_m
    if not (math.isfinite(acc) and 0 < acc <= hostel.max_location_accuracy_m):
        raise AppError(
            422, "location_unusable",
            "Location accuracy is too poor to mark attendance.",
            {"accuracy_m": _num(acc),
             "max_location_accuracy_m": hostel.max_location_accuracy_m},
        )
    ctx["accuracy_m"] = _num(acc)

    # -- Step 5: conservative geofence (server coordinates) ----------------
    decision = geofence.evaluate(
        payload.location.latitude, payload.location.longitude, acc,
        hostel.latitude, hostel.longitude, hostel.permitted_radius_m,
    )
    ctx["distance_m"] = _num(decision.distance_m)
    if not decision.inside:
        raise AppError(
            403, "outside_geofence",
            "You are outside the permitted hostel area.",
            {"distance_m": _num(decision.distance_m),
             "permitted_radius_m": hostel.permitted_radius_m},
        )

    # -- Step 6: face enrollment exists -------------------------------------
    enrollment = db.scalar(
        select(FaceEnrollment).where(FaceEnrollment.student_id == student.id)
    )
    if enrollment is None:
        raise AppError(403, "face_not_enrolled",
                       "Your face is not enrolled yet. Ask your hostel warden "
                       "to enroll you at the hostel office before marking "
                       "attendance.")

    # -- Step 7: embedding dim / finite / cosine >= threshold ---------------
    emb = payload.face.embedding
    stored_dim = enrollment.embedding_dim or settings.default_face_dim
    if payload.face.embedding_dim != stored_dim or len(emb) != stored_dim:
        raise AppError(
            403, "face_mismatch", "Face does not match the enrolled template.",
            {"similarity": None, "reason": "embedding_dim_mismatch",
             "expected_dim": stored_dim, "received_dim": payload.face.embedding_dim},
        )
    if not similarity.all_finite(emb):
        raise AppError(403, "face_mismatch", "Face does not match the enrolled template.",
                       {"similarity": None, "reason": "non_finite_embedding"})

    stored = template_crypto.decrypt_embedding(enrollment.embedding)
    sim = similarity.cosine_similarity(stored, emb)
    if not (math.isfinite(sim) and sim >= hostel.face_match_threshold):
        raise AppError(
            403, "face_mismatch", "Face does not match the enrolled template.",
            {"similarity": _num(sim), "threshold": hostel.face_match_threshold},
        )

    # -- Step 8: liveness policy -------------------------------------------
    liveness = payload.face.liveness
    if hostel.require_liveness:
        passed = (
            liveness.passed is True
            and liveness.method == LIVENESS_METHOD
            and math.isfinite(liveness.score)
            and 0.0 <= liveness.score <= LIVENESS_MAX_SCORE
        )
        if not passed:
            raise AppError(
                403, "liveness_failed", "Liveness check failed. Retry with your live face.",
                {"method": liveness.method, "score": _num(liveness.score),
                 "passed": liveness.passed},
            )
        outcome = "verified"
    else:
        # Never silently "verified" — warden must review.
        outcome = "pending_review"

    # -- Step 9: duplicate prevention + unique insert in one transaction ----
    day = local_date(hostel, now)
    existing = db.scalar(
        select(AttendanceRecord.id).where(
            AttendanceRecord.student_id == student.id,
            AttendanceRecord.attendance_date == day,
        )
    )
    if existing is not None:
        raise duplicate_attendance(day.isoformat())

    return _insert_record(db, student, hostel, day, now, outcome, ctx, sim, liveness)


def _insert_record(
    db: Session,
    student: Student,
    hostel: Hostel,
    day: date,
    now: datetime,
    outcome: str,
    ctx: dict[str, Any],
    similarity_value: float,
    liveness: Any,
) -> AttendanceRecord:
    """Insert the record inside a savepoint, allocating a unique reference.

    Races on ``UNIQUE(student_id, attendance_date)`` surface as an
    ``IntegrityError`` and are converted to ``duplicate_attendance`` (409);
    reference collisions retry with a short random suffix.
    """
    local = now.astimezone(hostel_tz(hostel))
    base = make_reference(local)
    reference = base
    collisions = 0

    while True:
        record = AttendanceRecord(
            reference=reference,
            student_id=student.id,
            hostel_id=hostel.id,
            attendance_date=day,
            recorded_at=now,
            outcome=outcome,
            distance_m=ctx["distance_m"],
            accuracy_m=ctx["accuracy_m"],
            face_similarity=similarity_value if math.isfinite(similarity_value) else None,
            liveness_score=_num(liveness.score),
            liveness_method=liveness.method,
            gate=None,
        )
        try:
            with db.begin_nested():
                db.add(record)
                db.flush()
        except IntegrityError as exc:
            if _unique_violation_name(exc) == "uq_attendance_student_date":
                raise duplicate_attendance(day.isoformat()) from exc
            collisions += 1
            if collisions >= 5:
                raise conflict("Could not allocate a unique attendance reference.") from exc
            reference = make_reference(local, _new_suffix())
            continue
        return record


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------

def record_to_public(record: AttendanceRecord, hostel: Hostel | None) -> dict[str, Any]:
    """Serialize an attendance record to the <AttendancePublic> shape."""
    tz = hostel_tz(hostel) if hostel else timezone.utc
    local = record.recorded_at.astimezone(tz)
    return {
        "id": record.id,
        "reference": record.reference,
        "date": record.attendance_date,
        "recorded_at": clock.utc_z(record.recorded_at),
        "recorded_at_local": local.isoformat(),
        "status": "present" if record.outcome == "verified" else "pending",
        "outcome": record.outcome,
        "distance_m": record.distance_m,
        "accuracy_m": record.accuracy_m,
        "face_similarity": record.face_similarity,
        "liveness_method": record.liveness_method,
        "liveness_score": record.liveness_score,
        "gate": record.gate,
        "reason": None,
    }


def absent_entry(day: date, reason: str = ABSENT_REASON) -> dict[str, Any]:
    """Synthesized absent day (no id, no record)."""
    return {
        "id": None,
        "reference": None,
        "date": day,
        "recorded_at": None,
        "recorded_at_local": None,
        "status": "absent",
        "outcome": None,
        "distance_m": None,
        "accuracy_m": None,
        "face_similarity": None,
        "liveness_method": None,
        "liveness_score": None,
        "gate": None,
        "reason": reason,
    }


# --------------------------------------------------------------------------
# Read models: status / summary / history
# --------------------------------------------------------------------------

def parse_date_param(value: str | None, field: str = "date") -> date | None:
    """Parse a ``YYYY-MM-DD`` query value or raise a 400 envelope error."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise invalid_payload(f"Invalid {field}: expected YYYY-MM-DD.") from exc


def parse_month_param(value: str | None, default_month: str) -> str:
    """Parse a ``YYYY-MM`` query value (defaults to ``default_month``)."""
    month = value or default_month
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise invalid_payload("Invalid month: expected YYYY-MM.") from exc
    return month


def month_bounds(month: str) -> tuple[date, date]:
    """First and last day of a ``YYYY-MM`` month."""
    year, mon = (int(part) for part in month.split("-"))
    last_day = calendar.monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last_day)


def build_status(
    db: Session,
    student: Student,
    hostel: Hostel | None,
    day: date | None,
) -> dict[str, Any]:
    """GET /attendance/status payload (defaults to today in hostel tz)."""
    if hostel is None:
        raise AppError(403, "hostel_not_configured", "No hostel is assigned to this student.")
    now = clock.utcnow()
    today = local_date(hostel, now)
    target = day or today

    record = db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.attendance_date == target,
    ))
    enrolled = db.scalar(select(FaceEnrollment.id).where(
        FaceEnrollment.student_id == student.id)) is not None

    win = window_state(hostel, now)
    is_today = target == today
    open_now = bool(win["open"] and is_today)
    marked = record is not None
    active = student.user.account_status == "active"
    can_mark = open_now and not marked and enrolled and active

    return {
        "date": target,
        "marked": marked,
        "outcome": record.outcome if record else None,
        "record": record_to_public(record, hostel) if record else None,
        "window": {**win, "open": open_now,
                   "minutes_remaining": win["minutes_remaining"] if open_now else 0},
        "can_mark": can_mark,
        "face_enrolled": enrolled,
    }


def build_summary(db: Session, student: Student, hostel: Hostel | None, month: str) -> dict[str, Any]:
    """GET /attendance/summary payload.

    ``absent`` = elapsed attendance days (window fully past; today only after
    close) with no record and no outpass (outpass is always 0 in v1).
    ``rate_percent`` = days accounted / total days in month, matching the
    worked example in docs/API.md (26 present + 1 absent of 29 => 93.1).
    """
    if hostel is None:
        raise AppError(403, "hostel_not_configured", "No hostel is assigned to this student.")
    now = clock.utcnow()
    first, last = month_bounds(month)
    today = local_date(hostel, now)

    records = db.scalars(select(AttendanceRecord).where(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.attendance_date >= first,
        AttendanceRecord.attendance_date <= last,
    )).all()
    recorded_days = {r.attendance_date for r in records}
    present = sum(1 for r in records if r.outcome == "verified")
    pending = sum(1 for r in records if r.outcome == "pending_review")

    absent = 0
    scan_end = min(last, today)
    if scan_end >= first:
        for offset in range((scan_end - first).days + 1):
            day = first + timedelta(days=offset)
            if day in recorded_days:
                continue
            if is_window_elapsed(hostel, day, now):
                absent += 1

    total_days = (last - first).days + 1
    days_accounted = present + pending + absent
    rate = round(100.0 * days_accounted / total_days, 1) if total_days else 0.0
    return {
        "month": month,
        "present": present,
        "absent": absent,
        "outpass": 0,
        "rate_percent": rate,
        "days_accounted": days_accounted,
        "total_days": total_days,
        "pass_threshold_percent": settings.pass_threshold_percent,
        "eligibility_safe": rate >= settings.pass_threshold_percent,
    }


def month_entries(
    db: Session,
    student: Student,
    hostel: Hostel | None,
    first: date,
    last: date,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Records + synthesized absents for one student over ``first..last``.

    Days with a record are always included; days without a record are included
    only once their window has fully elapsed. Students without a hostel
    contribute records only (no window math is possible).
    """
    now = now or clock.utcnow()
    records = db.scalars(select(AttendanceRecord).where(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.attendance_date >= first,
        AttendanceRecord.attendance_date <= last,
    )).all()
    by_day = {r.attendance_date: r for r in records}

    entries: list[dict[str, Any]] = []
    if last >= first:
        for offset in range((last - first).days + 1):
            day = first + timedelta(days=offset)
            record = by_day.get(day)
            if record is not None:
                entries.append(record_to_public(record, hostel))
            elif hostel is not None and is_window_elapsed(hostel, day, now):
                entries.append(absent_entry(day))
    return entries


def build_history(
    db: Session,
    student: Student,
    hostel: Hostel | None,
    month: str,
    status: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """GET /attendance/history payload with synthesized absents + pagination."""
    if hostel is None:
        raise AppError(403, "hostel_not_configured", "No hostel is assigned to this student.")
    first, last = month_bounds(month)
    entries = month_entries(db, student, hostel, first, last)
    if status is not None:
        entries = [e for e in entries if e["status"] == status]
    entries.sort(key=lambda e: e["date"], reverse=True)

    total = len(entries)
    total_pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    items = entries[start:start + page_size]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_more": page < total_pages,
    }
