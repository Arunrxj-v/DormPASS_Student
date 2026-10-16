"""students — student profile rows (roll number, hostel assignment, room)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core import clock
from ..core.roles import STATUS_CREATED
from ..db.base import Base
from .hostels import Hostel
from .users import User


class Student(Base):
    """Profile for a student user. ``student_id`` is the roll number.

    ``email`` is the normalized @ceconline.edu college address (unique).
    ``enrollment_status`` drives the provisioning lifecycle; a student may only
    authenticate once it reaches ``active``.
    """

    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=lambda: uuid.uuid4())
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    student_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    #: Normalized college email (unique, lowercased, @ceconline.edu only).
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True, nullable=True)
    #: Provisioning lifecycle — see core.roles (created -> ... -> active).
    enrollment_status: Mapped[str] = mapped_column(
        String(32), default=STATUS_CREATED, nullable=False, index=True
    )
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cohort: Mapped[str | None] = mapped_column(String(64), nullable=True)
    room: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hostel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hostels.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow(), onupdate=lambda: clock.utcnow()
    )

    user: Mapped[User] = relationship(User, lazy="joined")
    hostel: Mapped[Hostel | None] = relationship(Hostel, lazy="joined")
