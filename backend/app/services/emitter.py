import json
import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentEvent
from app.models.agent_event import AgentEvent as AgentEventModel
from app.services.redis_client import get_redis

logger = structlog.get_logger(__name__)

REDIS_SEQ_PREFIX = "meridian:seq:"
REDIS_CHANNEL_PREFIX = "meridian:session:"


class EventEmitterImpl:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._lock = asyncio.Lock()

    async def emit(self, event: AgentEvent) -> None:
        async with self._lock:
            redis = await get_redis()

            seq_key = f"{REDIS_SEQ_PREFIX}{event.session_id}"
            sequence_number = int(
                await cast(Awaitable[int], redis.incr(seq_key))
            )

            ts = datetime.now(UTC).isoformat()

            db_event = AgentEventModel(
                session_id=event.session_id,
                agent_type=event.agent_type,
                event_type=event.event_type,
                payload=event.payload,
                sequence_number=sequence_number,
            )
            self._db.add(db_event)
            await self._db.flush()

            sse_payload = json.dumps({
                "agent_type": event.agent_type,
                "event_type": event.event_type,
                "sequence_number": sequence_number,
                "timestamp": ts,
                "payload": event.payload,
            })
            channel = f"{REDIS_CHANNEL_PREFIX}{event.session_id}"
            await cast(Awaitable[int], redis.publish(channel, sse_payload))

        logger.debug(
            "event.emitted",
            session_id=str(event.session_id),
            event_type=event.event_type,
            seq=sequence_number,
        )
