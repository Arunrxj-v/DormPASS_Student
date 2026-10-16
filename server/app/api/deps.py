"""Shared FastAPI dependencies: authentication, roles, rate limits."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.errors import AppError, forbidden, rate_limited, token_invalid, token_revoked
from ..core.rate_limit import limiter
from ..core.roles import ROLE_ADMIN, ROLE_STUDENT, ROLE_WARDEN
from ..core.security import TokenClaims, decode_access_token
from ..db.session import get_session
from ..models import RevokedToken, Student, User


def account_inactive_error(role: str) -> AppError:
    """403 for a deactivated account, naming the right office to contact.

    Wardens have no "hostel warden" to contact about themselves; students
    have no administrator to contact. Both login and live-session checks use
    this copy so a deactivated account always gets the same, correct message.
    """
    contact = "your hostel warden" if role == ROLE_STUDENT else "an administrator"
    return AppError(403, "account_inactive", f"Account is inactive. Contact {contact}.")


@dataclass(frozen=True)
class AuthContext:
    """A validated bearer token plus its owning user."""

    user: User
    claims: TokenClaims


def get_auth_context(request: Request, db: Session = Depends(get_session)) -> AuthContext:
    """Validate ``Authorization: Bearer <jwt>`` — signature, expiry, revocation.

    Identity ALWAYS comes from the token; body fields are never identity.
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise token_invalid("Missing bearer token.")
    token = header[len("Bearer "):].strip()
    if not token:
        raise token_invalid("Missing bearer token.")

    claims = decode_access_token(token)

    revoked = db.scalar(select(RevokedToken.id).where(RevokedToken.jti == claims.jti))
    if revoked is not None:
        raise token_revoked()

    try:
        user_uuid = UUID(claims.user_id)
    except ValueError as exc:
        raise token_invalid() from exc
    user = db.get(User, user_uuid)
    if user is None:
        raise token_invalid("Token subject no longer exists.")
    if user.account_status != "active":
        # Deactivating or suspending an account must cut LIVE sessions too,
        # not only future sign-ins. Without this a dismissed warden keeps a
        # working bearer token until it expires, and could keep enrolling
        # faces or reading rosters after losing the role. (`/auth/refresh`
        # re-checks the same state, so the session cannot be extended.)
        raise account_inactive_error(user.role)
    return AuthContext(user=user, claims=claims)


def get_current_user(ctx: AuthContext = Depends(get_auth_context)) -> User:
    """Authenticated user (any role)."""
    return ctx.user


def get_current_student(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_session),
) -> Student:
    """Authenticated student profile. 403 for admins, 404 if the row is gone."""
    if ctx.user.role != "student":
        raise forbidden("This endpoint requires a student account.")
    student = db.scalar(select(Student).where(Student.user_id == ctx.user.id))
    if student is None:
        from ..core.errors import not_found

        raise not_found("Student")
    return student


def require_admin(ctx: AuthContext = Depends(get_auth_context)) -> User:
    """Admin-only role gate — wardens and students get 403 here."""
    if ctx.user.role != "admin":
        raise forbidden("Admin access required.")
    return ctx.user


def require_staff(ctx: AuthContext = Depends(get_auth_context)) -> User:
    """Admin OR warden role gate — students get 403 here."""
    if ctx.user.role not in (ROLE_ADMIN, ROLE_WARDEN):
        raise forbidden("Warden or administrator access required.")
    return ctx.user


def verify_rate_limit(
    request: Request,
    student: Student = Depends(get_current_student),
) -> None:
    """10 verify calls / student / minute (in-process sliding window)."""
    if not limiter.allow(f"verify:{student.id}",
                         settings.rate_limit_verify_per_minute, 60):
        raise rate_limited(settings.rate_limit_verify_per_minute, 60)


def login_rate_limit(request: Request, student_id: str) -> None:
    """5 login attempts / minute per (ip, student_id)."""
    ip = request.client.host if request.client else "unknown"
    key = f"login:{ip}:{student_id.strip().lower()}"
    if not limiter.allow(key, settings.rate_limit_login_per_minute, 60):
        raise rate_limited(settings.rate_limit_login_per_minute, 60)
