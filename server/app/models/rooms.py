"""rooms — managed room identifiers inside a hostel block.

``students.room`` stays a plain string (no schema rewrite, no data migration of
existing rosters); this table is the *registry* an admin manages. When a hostel
has rooms registered, student create/update rejects a room that is not one of
them, so a warden cannot park a student in an arbitrary string. When a hostel
has no registered rooms, free-text rooms keep working exactly as before.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core import clock
from ..db.base import Base
from .hostels import Hostel


class Room(Base):
    """One room identifier in a hostel, with an optional advisory capacity."""

    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("hostel_id", "identifier", name="uq_room_hostel_identifier"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=lambda: uuid.uuid4())
    hostel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hostels.id", ondelete="CASCADE"), index=True
    )
    identifier: Mapped[str] = mapped_column(String(32))
    #: Advisory occupancy limit; the backend does not hard-block over-capacity
    #: assignment (hostels over-subscribe in practice) — it is display policy.
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow(), onupdate=lambda: clock.utcnow()
    )

    hostel: Mapped[Hostel] = relationship(Hostel, lazy="joined")
