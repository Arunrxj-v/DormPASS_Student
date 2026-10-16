"""In-memory sliding-window rate limiter.

Single-process by design (the API runs with one uvicorn worker, as documented
in docs/ARCHITECTURE.md). Not shared across processes — intentional v1 limit.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Thread-safe fixed-capacity sliding window over monotonic-ish timestamps."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        """Record a hit for ``key``; return False if it exceeds ``limit``."""
        now = _now()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def remaining(self, key: str, limit: int, window_seconds: float) -> int:
        """How many hits are left in the current window (does not record)."""
        now = _now()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            return max(0, limit - len(bucket))

    def clear(self, key: str | None = None) -> None:
        """Drop one key or all counters (used by tests)."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


def _now() -> float:
    import time

    return time.monotonic()


# Process-wide limiter instance.
limiter = SlidingWindowRateLimiter()
