"""warden_hostels — which hostels a warden/admin may manage.

Authorization is hostel-scoped: a warden only sees and mutates students in the
hostels assigned here. Admins are additionally treated as global (see
``services.authorization``), so this table only needs rows for wardens.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core import clock
from ..db.base import Base


class WardenHostel(Base):
    """A single warden-to-hostel authorization grant."""

    __tablename__ = "warden_hostels"
    __table_args__ = (UniqueConstraint("user_id", "hostel_id", name="uq_warden_hostel"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=lambda: uuid.uuid4())
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    hostel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hostels.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow()
    )
