"""GET /health — app + database connectivity (Docker health checks)."""

from __future__ import annotations

from fastapi import APIRouter

from ..core.config import settings
from ..db.session import db_up
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness/readiness probe: 200 with ``database: up|down``."""
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        database="up" if db_up() else "down",
    )
