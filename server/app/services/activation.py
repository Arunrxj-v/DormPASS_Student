"""Account activation tokens — issue, redeem, and expire.

A warden creates a student and enrolls their face; the student then redeems a
single-use, time-limited token to set their own password and become ACTIVE.

Security properties enforced here:
  * 256-bit ``secrets`` token, returned exactly once to the caller.
  * Only SHA-256 of the token is stored (a DB leak yields no live links).
  * Bound to one user; unusable for any other account.
  * Single-use: ``used_at`` is set inside the same transaction that consumes it.
  * Time-limited: ``expires_at`` checked against the app clock.
  * Existing unused tokens for the same user are revoked when a new one is
    issued (only the most recent link works).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..core import clock
from ..core.config import settings
from ..core.errors import AppError, not_found
from ..models import AccountActivationToken, Student, User


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_token(token: str) -> str:
    """Public wrapper so tests can assert a stored hash never equals the token."""
    return _hash(token)


def issue_activation_token(
    db: Session,
    *,
    user_id,
    actor_user_id,
    ttl_seconds: int | None = None,
) -> tuple[str, datetime]:
    """Create a fresh activation token. Returns ``(plaintext, expires_at)``.

    The plaintext is returned ONCE and never persisted or logged.
    """
    ttl = ttl_seconds if ttl_seconds is not None else settings.activation_token_ttl_seconds
    now = clock.utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Only the newest link works.
    db.execute(
        update(AccountActivationToken)
        .where(AccountActivationToken.user_id == user_id,
               AccountActivationToken.used_at.is_(None))
        .values(used_at=now - timedelta(seconds=1))
    )

    plaintext = secrets.token_urlsafe(32)
    expires_at = now + timedelta(seconds=ttl)
    db.add(
        AccountActivationToken(
            user_id=user_id,
            token_hash=_hash(plaintext),
            created_at=now,
            expires_at=expires_at,
            created_by=actor_user_id,
        )
    )
    db.flush()
    return plaintext, expires_at


def _expired(record: AccountActivationToken) -> bool:
    expires = record.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    now = clock.utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now > expires


def redeem_activation_token(db: Session, token: str) -> AccountActivationToken:
    """Validate a token for redemption WITHOUT consuming it.

    Raises the same generic error for unknown, expired, already-used and
    wrong-account tokens so the endpoint cannot be used to probe state.
    """
    record = db.scalar(
        select(AccountActivationToken).where(
            AccountActivationToken.token_hash == _hash(token)
        )
    )
    if (
        record is None
        or record.used_at is not None
        or _expired(record)
    ):
        raise AppError(
            400,
            "activation_token_invalid",
            "This activation link is invalid or has expired. "
            "Ask your warden to issue a new one.",
        )
    return record


def consume_activation_token(db: Session, record: AccountActivationToken) -> None:
    """Mark a validated token used. Caller must commit."""
    now = clock.utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    record.used_at = now
    db.flush()


def activate_student_account(
    db: Session,
    *,
    record: AccountActivationToken,
    password_hash: str,
) -> tuple[User, Student]:
    """Set the password and move the student to ACTIVE.

    Every precondition is re-checked server-side against the token's OWN user
    — the token binds identity, not the request body.
    """
    user = db.get(User, record.user_id)
    if user is None:
        raise not_found("Account")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise AppError(409, "activation_not_permitted",
                       "This account has no student record. Contact your administrator.")

    if student.enrollment_status == "active":
        raise AppError(409, "already_active", "This account is already active.")
    if student.enrollment_status == "suspended":
        raise AppError(403, "account_suspended",
                       "This account is suspended. Contact your hostel warden.")
    if student.enrollment_status != "account_provisioned":
        # Face not enrolled / details unverified => activation is premature.
        raise AppError(403, "not_provisioned",
                       "This account is not ready for activation yet. "
                       "Contact your hostel warden.")

    user.password_hash = password_hash
    user.account_status = "active"
    student.enrollment_status = "active"
    consume_activation_token(db, record)
    db.flush()
    return user, student


def has_unused_token(db: Session, user_id) -> bool:
    """Whether a live (unused, unexpired) activation token exists."""
    from sqlalchemy import and_

    now = clock.utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (
        db.scalar(
            select(AccountActivationToken.id).where(
                and_(
                    AccountActivationToken.user_id == user_id,
                    AccountActivationToken.used_at.is_(None),
                    AccountActivationToken.expires_at > now,
                )
            )
        )
        is not None
    )
