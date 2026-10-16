"""account_activation_tokens — single-use, time-limited password-setup tokens.

A warden creates a student account and enrolls their face; the student then
redeems one of these tokens to set their own password and activate the account.
Only a SHA-256 hash of the token is stored, so a database leak does not hand
out live activation links. Tokens are bound to one user, expire, and are
invalidated after use.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core import clock
from ..db.base import Base


class AccountActivationToken(Base):
    """One redemption attempt's token record."""

    __tablename__ = "account_activation_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=lambda: uuid.uuid4())
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: clock.utcnow()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
