import asyncio
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import cast

import structlog
from sqlalchemy import select

from app.agents.base import AgentEvent
from app.agents.planner import PlannerAgent
from app.core.config import get_settings
from app.models.research_session import ResearchSession
from app.models.user_subscription import UserSubscription
from app.services.db import AsyncSessionFactory
from app.services.emitter import EventEmitterImpl
from app.services.redis_client import get_redis
from app.services.research_service import REDIS_QUEUE_KEY
from app.workers.research_worker import run_research_session

logger = structlog.get_logger(__name__)

QUEUE_POLL_TIMEOUT_SECONDS = 5


async def run_forever() -> None:
    """Continuously process queued research sessions from Redis."""
    logger.info("worker.started")
    while True:
        try:
            session_id = await _pop_session_id()
            if session_id is None:
                continue
            await process_session(session_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("worker.loop_error", error=str(exc))
            await asyncio.sleep(1)


async def _pop_session_id() -> uuid.UUID | None:
    redis = await get_redis()
    item = await cast(
        Awaitable[tuple[str, str] | None],
        redis.brpop(REDIS_QUEUE_KEY, timeout=QUEUE_POLL_TIMEOUT_SECONDS),
    )
    if item is None:
        return None

    _, raw_session_id = item
    try:
        return uuid.UUID(raw_session_id)
    except ValueError:
        logger.warning("worker.invalid_session_id", raw_session_id=raw_session_id)
        return None


async def process_session(session_id: uuid.UUID) -> None:
    """Run planner and research orchestration for a single queued session."""
    settings = get_settings()

    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(ResearchSession).where(ResearchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            logger.warning("worker.session_missing", session_id=str(session_id))
            return
        if session.status not in {"queued", "running"}:
            logger.info(
                "worker.session_skipped",
                session_id=str(session_id),
                status=session.status,
            )
            return

        pro_mode = False
        if session.user_id is not None:
            sub = await db.get(UserSubscription, session.user_id)
            pro_mode = sub is not None and sub.plan == "pro"

        emitter = EventEmitterImpl(db)
        try:
            session.status = "running"
            await db.flush()

            planner = PlannerAgent(
                session_id=session.id,
                emitter=emitter,
                max_sub_tasks=5 if pro_mode else 3,
            )
            plan = await planner.run({"question": session.question})
            sub_tasks = list(plan["sub_tasks"])
            session.sub_tasks = sub_tasks
            await db.flush()

            await run_research_session(
                session_id=session.id,
                question=session.question,
                sub_tasks=sub_tasks,
                emitter=emitter,
                db=db,
                settings=settings,
                pro_mode=pro_mode,
            )
            await db.commit()
            logger.info("worker.session_completed", session_id=str(session_id))
        except Exception as exc:
            await db.rollback()
            await _mark_failed(session_id, str(exc))


async def _mark_failed(session_id: uuid.UUID, error: str) -> None:
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(ResearchSession).where(ResearchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return

        session.status = "failed"
        session.error_message = error[:2000]
        session.completed_at = datetime.now(UTC)

        emitter = EventEmitterImpl(db)
        await emitter.emit(
            AgentEvent(
                session_id=session_id,
                agent_type="system",
                event_type="error",
                payload={"error": error[:2000]},
            )
        )
        await db.commit()
        logger.warning("worker.session_failed", session_id=str(session_id), error=error)
