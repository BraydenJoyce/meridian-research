from collections.abc import Awaitable
from typing import cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_session import ResearchSession
from app.schemas.research_session import CreateResearchResponse
from app.services.redis_client import get_redis

REDIS_QUEUE_KEY = "meridian:queue:sessions"

logger = structlog.get_logger(__name__)


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
