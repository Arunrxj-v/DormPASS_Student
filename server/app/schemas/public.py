"""Public (unauthenticated + shared) response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """GET /health 200 body."""

    status: str
    version: str
    database: str


class ConfigPublic(BaseModel):
    """GET /config/public 200 body (feature flags + branding)."""

    google_sso_enabled: bool
    app_min_version: str
    support_extension: str
    curfew_window_start: str | None = None
    curfew_window_end: str | None = None
    curfew_timezone: str | None = None


class GeofencePublic(BaseModel):
    """GET /hostels/me/geofence — server is the single source of truth."""

    hostel_id: UUID
    name: str
    block: str | None = None
    anchor_label: str | None = None
    latitude: float
    longitude: float
    permitted_radius_m: float
    max_location_accuracy_m: float
    boundary_policy: str
    timezone: str
    window_start: str
    window_end: str
    require_liveness: bool
    face_match_threshold: float
    warden_name: str | None = None
    warden_extension: str | None = None

    @classmethod
    def from_hostel(cls, hostel) -> "GeofencePublic":  # noqa: ANN001 - ORM model
        """Map a Hostel ORM row to the public geofence payload."""
        return cls(
            hostel_id=hostel.id,
            name=hostel.name,
            block=hostel.block,
            anchor_label=hostel.anchor_label,
            latitude=hostel.latitude,
            longitude=hostel.longitude,
            permitted_radius_m=hostel.permitted_radius_m,
            max_location_accuracy_m=hostel.max_location_accuracy_m,
            boundary_policy=hostel.boundary_policy,
            timezone=hostel.timezone,
            window_start=hostel.window_start,
            window_end=hostel.window_end,
            require_liveness=hostel.require_liveness,
            face_match_threshold=hostel.face_match_threshold,
            warden_name=hostel.warden_name,
            warden_extension=hostel.warden_extension,
        )


class FaceEnrollmentPublic(BaseModel):
    """GET/PUT /face-enrollment 200 body."""

    enrolled: bool
    model_version: str | None = None
    updated_at: str | None = None  # RFC 3339 UTC
