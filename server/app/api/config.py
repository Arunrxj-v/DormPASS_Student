"""GET /config/public — feature flags + minimal branding."""

from __future__ import annotations

from fastapi import APIRouter

from ..core.config import settings
from ..schemas import ConfigPublic

router = APIRouter(tags=["config"])


@router.get("/config/public", response_model=ConfigPublic)
def public_config() -> ConfigPublic:
    """Client bootstrap config (no auth).

    ``google_sso_enabled`` is derived from the actual capability — whether a
    Google OAuth audience is configured — rather than a separate boolean. Two
    independent flags would let a deployment advertise a button the backend
    rejects with 503, or hide one that would work.
    """
    return ConfigPublic(
        google_sso_enabled=bool(settings.google_oauth_client_id.strip()),
        app_min_version=settings.app_version,
        support_extension=settings.support_extension,
        curfew_window_start=settings.curfew_window_start,
        curfew_window_end=settings.curfew_window_end,
        curfew_timezone=settings.curfew_timezone,
    )
