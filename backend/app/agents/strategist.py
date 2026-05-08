"""StrategistAgent: converts research findings into recommendations, follow-ups, and risk flags."""
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
    "You are a senior strategy consultant reviewing a completed market intelligence report. "
    "Add three layers of value that the report itself does not provide: concrete next actions, "
    "follow-up research angles, and risk flags.\n\n"
    "Return JSON only — no markdown fencing, no preamble:\n"
    "{\n"
    '  "recommendations": [\n'
    "    {\n"
    '      "action": "<imperative, specific, under 100 chars>",\n'
    '      "rationale": "<1-2 sentences grounded in specific findings from the report>",\n'
    '      "priority": "<high|medium|low>"\n'
    "    }\n"
    "  ],\n"
    '  "follow_up_questions": [\n'
    '    "<a specific, immediately researchable follow-up question>"\n'
    "  ],\n"
    '  "risk_flags": [\n'
    "    {\n"
    '      "claim": "<specific claim or finding from the report>",\n'
    '      "concern": "<why this needs external validation before being acted on>"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- recommendations: 3-5 items; each action must be specific and operational, not generic "
    "advice like 'monitor the market'; every rationale must reference specific report findings\n"
    "- follow_up_questions: 3-5 items; each must be a question a researcher could immediately run\n"
    "- risk_flags: 0-4 items; only flag claims with material decision risk, not minor uncertainties\n"
    "- priority must be exactly one of: high, medium, low"
)

_EMPTY_RESULT: dict[str, Any] = {
    "recommendations": [],
    "follow_up_questions": [],
    "risk_flags": [],
}

_VALID_PRIORITIES = {"high", "medium", "low"}


class StrategistAgent(ResearchAgent):
    """
    Generates strategic recommendations, follow-up questions, and risk flags from the report.

    Runs in parallel with CriticAgent after WriterAgent completes. Non-fatal.
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
                agent_type="strategist",
                event_type="agent_started",
                payload={"agent": "strategist"},
            )
        )

        report_markdown = input_data.get("report_markdown", "")
        question = input_data.get("question", "")
        metrics: list[dict[str, Any]] = input_data.get("metrics", [])

        if not report_markdown:
            return await self._complete(_EMPTY_RESULT.copy())

        try:
            result = await self._analyze(report_markdown, question, metrics)
        except AgentError:
            raise
        except Exception as exc:
            logger.warning(
                "strategist.unexpected_error",
                session_id=str(self.session_id),
                error=str(exc),
            )
            raise AgentError(f"StrategistAgent failed: {exc}") from exc

        return await self._complete(result)

    async def _analyze(
        self,
        report_markdown: str,
        question: str,
        metrics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        report_excerpt = report_markdown[:4000]

        metrics_summary = ""
        if metrics:
            lines = [f"- {m['label']}: {m['value']}" for m in metrics[:10]]
            metrics_summary = "\n\nKey metrics extracted from sources:\n" + "\n".join(lines)

        user_text = (
            f"Research question: {question}\n\n"
            f"<report>\n{report_excerpt}\n</report>"
            f"{metrics_summary}\n\n"
            "Generate strategic recommendations, follow-up questions, and risk flags now."
        )

        try:
            message = await self._client.messages.create(
                model=get_settings().anthropic_strategist_model,
                max_tokens=2048,
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
                "strategist.api_error",
                session_id=str(self.session_id),
                error=str(exc),
            )
            raise AgentError(f"StrategistAgent API error: {exc}") from exc

    def _parse(self, raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw)

            recommendations = []
            for r in data.get("recommendations", [])[:5]:
                if not isinstance(r, dict):
                    continue
                if not r.get("action"):
                    continue
                priority = r.get("priority", "medium")
                if priority not in _VALID_PRIORITIES:
                    priority = "medium"
                recommendations.append({
                    "action": str(r["action"])[:120],
                    "rationale": str(r.get("rationale", "")),
                    "priority": priority,
                })

            follow_ups = [
                str(q) for q in data.get("follow_up_questions", [])[:5]
                if isinstance(q, str) and q.strip()
            ]

            risk_flags = []
            for f in data.get("risk_flags", [])[:4]:
                if not isinstance(f, dict):
                    continue
                if not f.get("claim"):
                    continue
                risk_flags.append({
                    "claim": str(f["claim"]),
                    "concern": str(f.get("concern", "")),
                })

            return {
                "recommendations": recommendations,
                "follow_up_questions": follow_ups,
                "risk_flags": risk_flags,
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("strategist.parse_error", raw=raw[:200])
            return _EMPTY_RESULT.copy()

    async def _complete(self, result: dict[str, Any]) -> dict[str, Any]:
        await self._store(result)

        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="strategist",
                event_type="strategy_ready",
                payload={
                    "recommendation_count": len(result.get("recommendations", [])),
                    "follow_up_count": len(result.get("follow_up_questions", [])),
                    **result,
                },
            )
        )
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="strategist",
                event_type="agent_completed",
                payload={"agent": "strategist"},
            )
        )

        logger.info(
            "strategist.completed",
            session_id=str(self.session_id),
            recommendation_count=len(result.get("recommendations", [])),
        )
        return result

    async def _store(self, result: dict[str, Any]) -> None:
        try:
            db_result = await self._db.execute(
                select(ResearchSession).where(ResearchSession.id == self.session_id)
            )
            session = db_result.scalar_one_or_none()
            if session is not None:
                session.strategy_json = result
                await self._db.flush()
        except Exception as exc:
            logger.warning("strategist.store_error", error=str(exc))
