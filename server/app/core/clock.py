"""Central clock.

All attendance decisions (window math, location freshness, reference
generation, history/summary synthesis) read time through ``clock.utcnow()`` so
tests can freeze the decision time deterministically. JWT issue/expiry times
deliberately use real wall-clock time instead.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def utc_z(value: datetime) -> str:
    """Format any aware datetime as RFC 3339 UTC with a trailing ``Z``."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
