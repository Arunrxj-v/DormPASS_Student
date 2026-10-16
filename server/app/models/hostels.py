"""hostels — geofence anchors plus attendance policy (single source of truth)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core import clock
from ..db.base import Base


class Hostel(Base):
    """One hostel block: where it is, when curfew attendance runs, and policy."""

    __tablename__ = "hostels"
    __table_args__ = (UniqueConstraint("name", "block", name="uq_hostel_name_block"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=lambda: uuid.uuid4())
    name: Mapped[str] = mapped_column(String(128))
    block: Mapped[str | None] = mapped_column(String(32), nullable=True)
    anchor_label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Geofence anchor + conservative boundary policy inputs.
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    permitted_radius_m: Mapped[float] = mapped_column(Float)
    max_location_accuracy_m: Mapped[float] = mapped_column(Float)
    boundary_policy: Mapped[str] = mapped_column(String(32), default="conservative")

    # Attendance window in the hostel's local timezone.
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    window_start: Mapped[str] = mapped_column(String(5), default="20:30")  # HH:MM
    window_end: Mapped[str] = mapped_column(String(5), default="22:30")  # HH:MM

    # Face policy.
    require_liveness: Mapped[bool] = mapped_column(Boolean, default=True)
    face_match_threshold: Mapped[float] = mapped_column(Float, default=0.75)

    warden_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    warden_extension: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow(), onupdate=lambda: clock.utcnow()
    )
