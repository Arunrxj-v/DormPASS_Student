"""Google ID-token verification for ``POST /auth/google``.

The app obtains an ID token; the SERVER independently verifies it. Nothing
about the account is taken from the client: the verified ``email`` claim is
the only identity input, and it is used solely to LOOK UP an existing
provisioned student. No account is ever created or linked by this path.

Verification (RS256 via Google's published JWKS):
  * signature — real JWKS key lookup with kid rotation support
  * ``iss``    — accounts.google.com or https://accounts.google.com
  * ``aud``    — must equal the configured OAuth client id
  * ``exp``/``iat`` — freshness, with a small clock-skew allowance
  * ``email_verified`` must be true
  * ``email`` hostname must be exactly ``ceconline.edu``

``verify_google_id_token`` is a thin wrapper around ``GoogleTokenVerifier``
so tests can substitute a fake verifier without weakening production code.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
import jwt

from ..core.config import settings
from ..core.errors import AppError, invalid_credentials
from ..core.roles import LOGINABLE_STATUSES, ROLE_STUDENT
from ..services.identity import PERMITTED_EMAIL_DOMAIN, normalize_email

logger = logging.getLogger("hostelpass.google")

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
VALID_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
_JWKS_CACHE_SECONDS = 3600
_SKEW_SECONDS = 60


class GoogleTokenError(Exception):
    """A token failed structural/signature verification."""


@dataclass(frozen=True)
class VerifiedGoogleIdentity:
    """Claims extracted from a token that passed full verification."""

    email: str
    subject: str
    name: str | None = None


class GoogleTokenVerifier:
    """Fetches Google's JWKS and verifies ID tokens against it (cached)."""

    def __init__(self, jwks_url: str = GOOGLE_JWKS_URL,
                 fetcher: Callable[[str], dict[str, Any]] | None = None) -> None:
        self._jwks_url = jwks_url
        self._fetcher = fetcher or self._default_fetch
        self._cache: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    @staticmethod
    def _default_fetch(url: str) -> dict[str, Any]:
        with httpx.Client(timeout=5.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()

    def _jwks(self) -> dict[str, Any]:
        with self._lock:
            if self._cache and time.monotonic() - self._fetched_at < _JWKS_CACHE_SECONDS:
                return self._cache
            try:
                data = self._fetcher(self._jwks_url)
            except Exception as exc:  # network/parse failure
                logger.warning("Google JWKS fetch failed: %s", type(exc).__name__)
                # Serve a stale cache if we have one rather than failing open.
                if self._cache:
                    return self._cache
                raise GoogleTokenError("google_keys_unavailable") from exc
            self._cache = data
            self._fetched_at = time.monotonic()
            return data

    def _key_for(self, header: dict[str, Any]):
        kid = header.get("kid")
        jwks = self._jwks()
        keys = jwks.get("keys") or []
        if kid is None:
            return keys[0] if len(keys) == 1 else None
        for key in keys:
            if key.get("kid") == kid:
                return key
        # Key rotation: force one refresh if the kid is unknown.
        with self._lock:
            self._fetched_at = 0.0
        jwks = self._jwks()
        for key in (jwks.get("keys") or []):
            if key.get("kid") == kid:
                return key
        return None

    def verify(self, id_token: str, audience: str) -> VerifiedGoogleIdentity:
        """Fully verify an ID token or raise ``GoogleTokenError``."""
        try:
            header = jwt.get_unverified_header(id_token)
        except Exception as exc:
            raise GoogleTokenError("malformed") from exc
        if header.get("alg") in (None, "none") or "RS256" not in str(header.get("alg")):
            raise GoogleTokenError("bad_alg")

        key = self._key_for(header)
        if key is None:
            raise GoogleTokenError("unknown_key")

        try:
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=["RS256"],
                audience=audience,
                issuer=None,  # validated manually to accept both issuer spellings
                leeway=_SKEW_SECONDS,
                options={"require": ["exp", "iat", "sub", "aud", "email"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise GoogleTokenError("expired") from exc
        except jwt.PyJWTError as exc:
            raise GoogleTokenError("invalid") from exc

        if claims.get("iss") not in VALID_ISSUERS:
            raise GoogleTokenError("bad_issuer")
        if not claims.get("email_verified", False):
            raise GoogleTokenError("email_not_verified")

        email = normalize_email(str(claims.get("email", "")))
        if not email.split("@", 1)[-1] == PERMITTED_EMAIL_DOMAIN:
            raise GoogleTokenError("bad_domain")

        return VerifiedGoogleIdentity(
            email=email,
            subject=str(claims.get("sub")),
            name=claims.get("name"),
        )


_verifier: GoogleTokenVerifier | None = None


def get_verifier() -> GoogleTokenVerifier:
    global _verifier
    if _verifier is None:
        _verifier = GoogleTokenVerifier()
    return _verifier


def set_verifier(verifier: GoogleTokenVerifier | None) -> None:
    """Install a test double. Production never calls this."""
    global _verifier
    _verifier = verifier


def verify_google_id_token(id_token: str) -> VerifiedGoogleIdentity:
    """Verify an ID token against the configured OAuth client id."""
    audience = settings.google_oauth_client_id.strip()
    if not audience:
        raise AppError(
            503,
            "google_signin_not_configured",
            "Google Sign-In is not configured for this deployment. "
            "Use your college email and password instead.",
        )
    try:
        return get_verifier().verify(id_token, audience)
    except GoogleTokenError as exc:
        logger.info("Google token rejected: %s", exc)
        raise invalid_credentials(
            "Google sign-in failed. Please try again or use your college email."
        ) from exc


def authenticate_google_user(db, identity: VerifiedGoogleIdentity):
    """Map a verified Google identity onto an EXISTING provisioned student.

    Never creates, never links, never upgrades. Returns ``(user, student)``.
    """
    from sqlalchemy import select

    from ..models import Student, User

    user = db.scalar(select(User).where(User.username == identity.email))
    if user is None:
        # Fall back to the student's registered college email.
        student = db.scalar(select(Student).where(Student.email == identity.email))
        if student is not None:
            user = db.get(User, student.user_id)
    else:
        student = db.scalar(select(Student).where(Student.user_id == user.id))

    # Unrecognised identity and unprovisioned identity get the SAME message so
    # Google Sign-In cannot be used to enumerate registered addresses.
    if user is None or user.role != ROLE_STUDENT:
        raise _not_provisioned()
    if student is None:
        raise _not_provisioned()
    if user.account_status != "active" or student.enrollment_status not in LOGINABLE_STATUSES:
        raise _not_provisioned()
    return user, student


def _not_provisioned() -> AppError:
    return AppError(
        403,
        "account_not_activated",
        "Your HostelPass account has not been activated. "
        "Please contact your hostel warden.",
    )
