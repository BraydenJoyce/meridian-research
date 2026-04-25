import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_event import AgentEvent
from app.models.research_session import ResearchSession

logger = structlog.get_logger(__name__)

POLL_INTERVAL = 0.5
TERMINAL_STATUSES = frozenset({"completed", "failed"})


async def event_stream(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    last_seq = 0

    try:
        while True:
            result = await db.execute(
                select(AgentEvent)
                .where(
                    AgentEvent.session_id == session_id,
                    AgentEvent.sequence_number > last_seq,
                )
                .order_by(AgentEvent.sequence_number)
            )
            events = list(result.scalars().all())

            for event in events:
                last_seq = max(last_seq, event.sequence_number)
                payload = {
                    "event_type": event.event_type,
                    "agent_type": event.agent_type,
                    "sequence_number": event.sequence_number,
                    "timestamp": (
                        event.created_at.isoformat()
                        if event.created_at
                        else datetime.now(UTC).isoformat()
                    ),
                    "payload": event.payload,
                }
                yield f"data: {json.dumps(payload)}\n\n"

            session_result = await db.execute(
                select(ResearchSession).where(ResearchSession.id == session_id)
            )
            session = session_result.scalar_one_or_none()
            if session is not None and session.status in TERMINAL_STATUSES:
                yield f"data: {json.dumps({'event_type': 'done', 'status': session.status})}\n\n"
                return

            await asyncio.sleep(POLL_INTERVAL)

    except GeneratorExit:
        logger.info("stream.client_disconnected", session_id=str(session_id))
