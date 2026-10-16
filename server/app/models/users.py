"""users — login identities and roles."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core import clock
from ..db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    """A login identity. Students have one of these; admins have only this."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="student")  # 'admin' | 'student'
    account_status: Mapped[str] = mapped_column(String(16), default="active")  # 'active' | 'inactive'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow(), onupdate=lambda: clock.utcnow()
    )
