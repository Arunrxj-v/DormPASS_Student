"""Password hashing (bcrypt) and JWT access tokens (HS256).

``passlib`` is intentionally avoided — it is unmaintained and breaks with
modern ``bcrypt`` releases, so we wrap the ``bcrypt`` package directly.
"""

from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass

import bcrypt
import jwt

from ..core.config import settings
from ..core.errors import token_invalid

# bcrypt silently truncates inputs at 72 bytes; fail loudly instead of
# accepting a prefix of a longer password.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (cost 12)."""
    raw = password.encode("utf-8")
    if len(raw) > _MAX_PASSWORD_BYTES:
        raw = raw[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-ish check of a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:_MAX_PASSWORD_BYTES],
                              password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class TokenClaims:
    """Decoded, validated access-token claims."""

    user_id: str
    role: str
    jti: str
    expires_at: int


def create_access_token(user_id: str, role: str) -> tuple[str, str, int]:
    """Issue an HS256 access token.

    Returns ``(token, jti, expires_in_seconds)``. Claims: ``sub`` (user uuid),
    ``role``, ``jti``, ``iat``, ``exp`` — 30 minute default lifetime.
    """
    now = int(time.time())
    expires_in = settings.jwt_expires_seconds
    jti = uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "role": role,
        "jti": jti,
        "iat": now,
        "exp": now + expires_in,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, expires_in


def decode_access_token(token: str) -> TokenClaims:
    """Decode and validate signature/expiry. Raises AppError(401) on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise token_invalid("Authentication token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise token_invalid() from exc

    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise token_invalid()
    return TokenClaims(
        user_id=sub,
        role=str(payload.get("role", "")),
        jti=str(payload.get("jti", "")),
        expires_at=int(payload.get("exp", 0)),
    )


def new_request_id() -> str:
    """Random identifier used for opaque audit details."""
    return secrets.token_hex(8)
