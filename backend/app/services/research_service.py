import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import cast

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_session import ResearchSession
from app.schemas.research_session import CreateResearchResponse
from app.services.redis_client import get_redis

REDIS_QUEUE_KEY = "meridian:queue:sessions"

logger = structlog.get_logger(__name__)


async def get_usage_this_month(user_id: uuid.UUID, db: AsyncSession) -> int:
    """Count research sessions created by user_id in the current calendar month."""
    start_of_month = datetime.now(UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    count = await db.scalar(
        select(func.count()).select_from(ResearchSession).where(
            ResearchSession.user_id == user_id,
            ResearchSession.created_at >= start_of_month,
        )
    )
    return int(count or 0)


async def create_research_session(
    question: str,
    db: AsyncSession,
) -> CreateResearchResponse:
    session = ResearchSession(question=question)
    db.add(session)
    await db.flush()  # assigns id without committing

    redis = await get_redis()
    await cast(Awaitable[int], redis.lpush(REDIS_QUEUE_KEY, str(session.id)))

    await db.commit()
    await db.refresh(session)

    logger.info("research_session.created", session_id=str(session.id))

    return CreateResearchResponse(
        session_id=session.id,
        status="queued",
        stream_url=f"/api/research/{session.id}/stream",
    )
