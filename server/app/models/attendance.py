"""attendance_records + attendance_attempts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core import clock
from ..db.base import Base


class AttendanceRecord(Base):
    """A recorded attendance decision for a student on an attendance date.

    Immutable for students; admins change it only through the audited
    approve/reject/correction endpoints.
    """

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("student_id", "attendance_date", name="uq_attendance_student_date"),
        UniqueConstraint("reference", name="uq_attendance_reference"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=lambda: uuid.uuid4())
    reference: Mapped[str] = mapped_column(String(32), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    hostel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hostels.id", ondelete="SET NULL"), nullable=True
    )
    attendance_date: Mapped[date] = mapped_column(Date)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # server clock
    outcome: Mapped[str] = mapped_column(String(24))  # 'verified' | 'pending_review'

    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    face_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liveness_method: Mapped[str | None] = mapped_column(String(48), nullable=True)
    gate: Mapped[str | None] = mapped_column(String(48), nullable=True)


class AttendanceAttempt(Base):
    """Every verify attempt, accepted or rejected.

    Deliberately stores NO raw coordinates — only distance/accuracy/outcome.
    """

    __tablename__ = "attendance_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=lambda: uuid.uuid4())
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow(), index=True
    )
    outcome: Mapped[str] = mapped_column(String(16))  # 'accepted' | 'rejected'
    rejection_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
