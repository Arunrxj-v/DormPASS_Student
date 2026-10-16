"""face_enrollments — Fernet-encrypted face templates, one per student."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core import clock
from ..db.base import Base


class FaceEnrollment(Base):
    """An enrolled student face template. ``embedding`` is Fernet-encrypted."""

    __tablename__ = "face_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=lambda: uuid.uuid4())
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), unique=True, index=True
    )
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    embedding_dim: Mapped[int] = mapped_column(default=128)
    model_version: Mapped[str] = mapped_column(String(64))
    quality: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow(), onupdate=lambda: clock.utcnow()
    )
