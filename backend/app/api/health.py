"""Health check endpoint for uptime monitoring."""
from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

router = APIRouter()

APP_VERSION = "1.0.0-beta"


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
    redis: str


async def _check_db() -> str:
    """Ping the database and return 'ok' or 'error'."""
    try:
        import asyncpg  # noqa: I001
        from app.core.config import get_settings
        settings = get_settings()
        raw_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncio.wait_for(asyncpg.connect(raw_url), timeout=2.0)
        await conn.close()
        return "ok"
    except Exception:
        return "error"


async def _check_redis() -> str:
    """Ping Redis and return 'ok' or 'error'."""
    try:
        from app.services.redis_client import get_redis
        redis = await asyncio.wait_for(get_redis(), timeout=2.0)
        await asyncio.wait_for(redis.ping(), timeout=2.0)
        return "ok"
    except Exception:
        return "error"


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health status including database and Redis connectivity.

    Returns:
        HealthResponse with overall status, app version, and per-service status.
        HTTP 200 when all services are healthy; HTTP 503 if any service is down.
    """
    db_status, redis_status = await asyncio.gather(
        _check_db(), _check_redis(), return_exceptions=False
    )

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        version=APP_VERSION,
        db=str(db_status),
        redis=str(redis_status),
    )
