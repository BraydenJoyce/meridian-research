"""HypothesisAgent: frames the research question before data collection begins."""
from __future__ import annotations

import json
import uuid
from typing import Any

import anthropic
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentError, AgentEvent, EventEmitter, ResearchAgent
from app.core.config import get_settings
from app.models.research_session import ResearchSession

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a research strategist framing a market intelligence brief. "
    "Given a research question and planned sub-tasks, generate a concise research frame "
    "shown to the analyst before results arrive.\n\n"
    "Return JSON only — no markdown fencing, no preamble:\n"
    "{\n"
    '  "hypothesis": "<one falsifiable sentence: the working assumption the research will test>",\n'
    '  "research_angles": ["<angle 1, under 80 chars>", "<angle 2>", "<angle 3>"],\n'
    '  "scope_note": "<1-2 sentences on boundaries — geography, time period, or company size>",\n'
    '  "assumed_audience": "<specific role, not \'business professionals\'>"\n'
    "}\n\n"
    "Rules: hypothesis must be testable and falsifiable; research_angles 2-4 items each under 80 "
    "characters; scope_note acknowledges at least one boundary; assumed_audience names a specific role."
)

_FALLBACK: dict[str, Any] = {
    "hypothesis": "",
    "research_angles": [],
    "scope_note": "",
    "assumed_audience": "",
}


class HypothesisAgent(ResearchAgent):
    """
    Frames the research question into a testable hypothesis and research angles.

    Runs synchronously after the Planner and before web search, giving users
    immediate context while slow parallel agents run. Non-fatal.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        emitter: EventEmitter,
        db: AsyncSession,
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db
        self._client = anthropic.AsyncAnthropic()

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="hypothesis",
                event_type="agent_started",
                payload={"agent": "hypothesis"},
            )
        )

        question = input_data.get("question", "")
        sub_tasks = input_data.get("sub_tasks", [])

        result = await self._frame(question, sub_tasks)
        await self._store(result)

        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="hypothesis",
                event_type="hypothesis_ready",
                payload=result,
            )
        )
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="hypothesis",
                event_type="agent_completed",
                payload={"agent": "hypothesis"},
            )
        )

        logger.info("hypothesis.completed", session_id=str(self.session_id))
        return result

    async def _frame(self, question: str, sub_tasks: list[str]) -> dict[str, Any]:
        tasks_text = "\n".join(f"- {t}" for t in sub_tasks)
        user_text = (
            f"Research question: {question}\n\n"
            f"Planned sub-tasks:\n{tasks_text}\n\n"
            "Generate the research frame now."
        )

        try:
            message = await self._client.messages.create(
                model=get_settings().anthropic_hypothesis_model,
                max_tokens=512,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_text}],
            )
            raw = ""
            for block in message.content:
                if hasattr(block, "type") and block.type == "text":
                    raw = block.text
                    break
            return self._parse(raw)
        except Exception as exc:
            logger.warning(
                "hypothesis.api_error",
                session_id=str(self.session_id),
                error=str(exc),
            )
            raise AgentError(f"HypothesisAgent API error: {exc}") from exc

    def _parse(self, raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw)
            return {
                "hypothesis": str(data.get("hypothesis", "")),
                "research_angles": [str(a) for a in data.get("research_angles", [])],
                "scope_note": str(data.get("scope_note", "")),
                "assumed_audience": str(data.get("assumed_audience", "")),
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("hypothesis.parse_error", raw=raw[:200])
            return _FALLBACK.copy()

    async def _store(self, data: dict[str, Any]) -> None:
        try:
            result = await self._db.execute(
                select(ResearchSession).where(ResearchSession.id == self.session_id)
            )
            session = result.scalar_one_or_none()
            if session is not None:
                session.hypothesis_json = data
                await self._db.flush()
        except Exception as exc:
            logger.warning("hypothesis.store_error", error=str(exc))
