"""CriticAgent: fact-checks WriterAgent output and flags unsupported claims (ADR-007)."""
from __future__ import annotations

import json
import uuid
from typing import Any

import anthropic
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentEvent, EventEmitter, ResearchAgent
from app.core.config import get_settings
from app.models.research_session import ResearchSession

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a fact-checking assistant reviewing a market intelligence report. "
    "Your task is to identify claims in the report that:\n"
    "1. Lack an inline citation (e.g., [Source](url))\n"
    "2. Appear to contradict information in the provided sources\n\n"
    "Return a JSON object with exactly this structure:\n"
    "{\n"
    '  "quality_score": <float between 0.0 and 1.0>,\n'
    '  "flagged_claims": [\n'
    '    {"claim": "<quoted text from report>", "reason": "<why flagged>"}\n'
    "  ]\n"
    "}\n\n"
    "quality_score: 1.0 means fully supported; 0.0 means almost no claims are supported. "
    "Return only valid JSON, no markdown fencing, no preamble."
)

_FALLBACK = {"quality_score": 1.0, "flagged_claims": []}


class CriticAgent(ResearchAgent):
    """
    Fact-checks a research report against its source material using Claude.

    Non-fatal: API errors and JSON parse failures return a permissive fallback
    ({quality_score: 1.0, flagged_claims: []}). Never raises AgentFatalError.
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
                agent_type="critic",
                event_type="agent_started",
                payload={"agent": "critic"},
            )
        )

        report_markdown = input_data.get("report_markdown", "")
        sources = input_data.get("sources", [])

        critique = await self._critique(report_markdown, sources)
        await self._store_critique(critique)

        quality_score = float(critique.get("quality_score", 1.0))
        flagged_count = len(critique.get("flagged_claims", []))

        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="critic",
                event_type="report_critique",
                payload={
                    "agent": "critic",
                    "quality_score": quality_score,
                    "flagged_count": flagged_count,
                    "flagged_claims": critique.get("flagged_claims", []),
                },
            )
        )
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="critic",
                event_type="agent_completed",
                payload={"agent": "critic", "quality_score": quality_score},
            )
        )
        return {
            "quality_score": quality_score,
            "flagged_claims": critique.get("flagged_claims", []),
        }

    async def _critique(
        self, report_markdown: str, sources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not report_markdown:
            return _FALLBACK

        sources_text = "\n\n".join(
            f"Source: {s.get('url', '')}\nTitle: {s.get('title', '')}\n{s.get('content', '')[:500]}"
            for s in sources[:10]
        )
        user_text = (
            f"<report>\n{report_markdown[:3000]}\n</report>\n\n"
            f"<sources>\n{sources_text}\n</sources>\n\n"
            "Identify unsupported or contradicted claims in the report."
        )

        try:
            message = await self._client.messages.create(
                model=get_settings().anthropic_critic_model,
                max_tokens=1024,
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
            return self._parse_json(raw)
        except Exception as exc:
            logger.warning(
                "critic_api_error", session_id=str(self.session_id), error=str(exc)
            )
            return _FALLBACK

    def _parse_json(self, raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw)
            score = float(data.get("quality_score", 1.0))
            score = max(0.0, min(1.0, score))
            data["quality_score"] = score
            if "flagged_claims" not in data:
                data["flagged_claims"] = []
            return data
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("critic_json_parse_error", raw=raw[:200])
            return _FALLBACK

    async def _store_critique(self, critique: dict[str, Any]) -> None:
        try:
            result = await self._db.execute(
                select(ResearchSession).where(ResearchSession.id == self.session_id)
            )
            session = result.scalar_one_or_none()
            if session is not None:
                session.critique_json = critique
                await self._db.flush()
        except Exception as exc:
            logger.warning("critic_store_error", error=str(exc))
