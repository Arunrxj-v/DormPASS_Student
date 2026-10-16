"""Attendance request/response schemas (status, summary, history, verify)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from .auth import validate_embedding


# --- verify evidence ---------------------------------------------------------

class LocationEvidence(BaseModel):
    """GPS fix claimed by the client. Never trusted beyond format."""

    latitude: float
    longitude: float
    accuracy_m: float
    timestamp_utc: datetime

    @field_validator("timestamp_utc")
    @classmethod
    def _tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp_utc must be RFC 3339 with a timezone")
        return value


class LivenessEvidence(BaseModel):
    """Passive anti-spoof output from the on-device model."""

    method: str
    score: float
    passed: bool


class FaceEvidence(BaseModel):
    """Face embedding evidence. Non-finite values pass schema validation on
    purpose — the verify pipeline rejects them as ``face_mismatch`` (step 7)."""

    embedding: list[float]
    embedding_dim: int
    model_version: str | None = None
    liveness: LivenessEvidence
    captured_at_utc: datetime | None = None

    @field_validator("captured_at_utc")
    @classmethod
    def _tz_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("captured_at_utc must be RFC 3339 with a timezone")
        return value

    @field_validator("embedding_dim")
    @classmethod
    def _dim_bounds(cls, value: int) -> int:
        if value < 1 or value > 4096:
            raise ValueError("embedding_dim must be between 1 and 4096")
        return value

    @model_validator(mode="after")
    def _len_matches_dim(self) -> "FaceEvidence":
        # Runs after every field is set, so embedding_dim is always present
        # regardless of declaration order. Finite-ness is deliberately NOT
        # checked here — the verify pipeline reports NaN/Inf as face_mismatch.
        if len(self.embedding) != self.embedding_dim:
            raise ValueError(
                f"embedding length {len(self.embedding)} does not match "
                f"embedding_dim {self.embedding_dim}"
            )
        return self


class DeviceInfo(BaseModel):
    """Optional device context (integrity attestation is informational in v1)."""

    model_config = {"extra": "allow"}

    app_version: str | None = None
    platform: str | None = None
    device_model: str | None = None
    integrity_verdict: str | None = None


class VerifyRequest(BaseModel):
    """POST /attendance/verify body — evidence only, never identity."""

    location: LocationEvidence
    face: FaceEvidence
    device: DeviceInfo | None = None


# --- attendance read models --------------------------------------------------

class AttendancePublic(BaseModel):
    """<AttendancePublic>; absent days are synthesized with no id/reference."""

    id: UUID | None = None
    reference: str | None = None
    date: date
    recorded_at: str | None = None  # RFC 3339 UTC, e.g. "2026-10-13T15:12:19Z"
    recorded_at_local: str | None = None
    status: Literal["present", "pending", "absent"]
    outcome: Literal["verified", "pending_review"] | None = None
    distance_m: float | None = None
    accuracy_m: float | None = None
    face_similarity: float | None = None
    liveness_method: str | None = None
    liveness_score: float | None = None
    gate: str | None = None
    reason: str | None = None


class WindowPublic(BaseModel):
    """Curfew window state in the hostel's timezone."""

    open: bool
    opens_at: str
    closes_at: str
    minutes_remaining: int
    timezone: str


class AttendanceStatusResponse(BaseModel):
    """GET /attendance/status body."""

    date: date
    marked: bool
    outcome: str | None = None
    record: AttendancePublic | None = None
    window: WindowPublic
    can_mark: bool
    face_enrolled: bool


class SummaryResponse(BaseModel):
    """GET /attendance/summary body (outpass is always 0 in v1)."""

    month: str
    present: int
    absent: int
    outpass: int
    rate_percent: float
    days_accounted: int
    total_days: int
    pass_threshold_percent: int
    eligibility_safe: bool


class HistoryResponse(BaseModel):
    """GET /attendance/history body (items may include synthesized absents)."""

    items: list[AttendancePublic]
    page: int
    page_size: int
    total_pages: int
    has_more: bool
