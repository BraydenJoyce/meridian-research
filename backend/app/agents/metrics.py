"""MetricsAgent: extracts structured quantitative data points from research sources."""
from __future__ import annotations

import asyncio
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
from app.models.source import Source

logger = structlog.get_logger(__name__)

_STARTUP_WAIT_SECONDS = 12
_MAX_SOURCES = 30
_MIN_QUALITY_SCORE = 0.4

SYSTEM_PROMPT = (
    "You are a quantitative research analyst. Extract structured, attributable metrics "
    "from the provided research sources.\n\n"
    "Return JSON only — no markdown fencing, no preamble:\n"
    "{\n"
    '  "metrics": [\n'
    "    {\n"
    '      "label": "<descriptive label, under 60 chars>",\n'
    '      "value": "<number as it appears, e.g. \'$89.4B\' or \'23.4% CAGR\'>",\n'
    '      "context": "<one sentence: what this number means>",\n'
    '      "source_url": "<exact URL from the source tag — never fabricate>",\n'
    '      "metric_type": "<market_size|growth_rate|share|funding|headcount|ranking|other>"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Return 0-20 metrics (quality over quantity)\n"
    "- Never fabricate source_url values — use only URLs that appear in the source tags\n"
    "- Deduplicate: if the same statistic appears in multiple sources, return it once using "
    "the most authoritative source URL\n"
    "- Skip vague statements like 'growing rapidly' or 'significant increase'\n"
    "- metric_type must be exactly one of: market_size, growth_rate, share, funding, "
    "headcount, ranking, other"
)

_VALID_METRIC_TYPES = {
    "market_size", "growth_rate", "share", "funding", "headcount", "ranking", "other"
}


class MetricsAgent(ResearchAgent):
    """
    Extracts quantitative metrics from scored sources after web search completes.

    Waits 12 seconds on startup to allow WebSearchAgent to flush sources to DB.
    Non-fatal: returns empty metrics list on any failure.
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
                agent_type="metrics",
                event_type="agent_started",
                payload={"agent": "metrics"},
            )
        )

        await asyncio.sleep(_STARTUP_WAIT_SECONDS)

        question = input_data.get("question", "")

        try:
            sources = await self._load_sources()
            if not sources:
                return await self._complete([])

            metrics = await self._extract(sources, question)
        except AgentError:
            raise
        except Exception as exc:
            logger.warning(
                "metrics.unexpected_error",
                session_id=str(self.session_id),
                error=str(exc),
            )
            raise AgentError(f"MetricsAgent failed: {exc}") from exc

        return await self._complete(metrics)

    async def _load_sources(self) -> list[Source]:
        result = await self._db.execute(
            select(Source)
            .where(Source.session_id == self.session_id)
            .order_by(Source.sub_task_index)
        )
        all_sources = list(result.scalars().all())
        scored = [
            s for s in all_sources
            if s.relevance_score is not None and float(s.relevance_score) > _MIN_QUALITY_SCORE
        ]
        if not scored:
            scored = all_sources
        return scored[:_MAX_SOURCES]

    async def _extract(self, sources: list[Source], question: str) -> list[dict[str, Any]]:
        sources_block = _format_sources_block(sources)

        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": sources_block,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": (
                    f"Research question: {question}\n\n"
                    "Extract all specific quantitative metrics from the sources above."
                ),
            },
        ]

        try:
            message = await self._client.messages.create(
                model=get_settings().anthropic_metrics_model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
            )
            raw = ""
            for block in message.content:
                if hasattr(block, "type") and block.type == "text":
                    raw = block.text
                    break
            return self._parse(raw)
        except Exception as exc:
            logger.warning(
                "metrics.api_error",
                session_id=str(self.session_id),
                error=str(exc),
            )
            raise AgentError(f"MetricsAgent API error: {exc}") from exc

    def _parse(self, raw: str) -> list[dict[str, Any]]:
        raw = raw.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]

        # Try clean parse first; fall back to salvaging complete objects from truncated JSON
        candidates: list[str] = [raw]
        bracket = raw.find("[")
        if bracket != -1:
            # Close any truncated array/object so json.loads has a fighting chance
            partial = raw[bracket:]
            candidates.append(partial + "]}") if not partial.rstrip().endswith("]") else None

        metrics_raw: list[Any] = []
        for attempt in candidates:
            try:
                data = json.loads(attempt)
                metrics_raw = data.get("metrics", []) if isinstance(data, dict) else []
                break
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

        if not metrics_raw:
            logger.warning("metrics.parse_error", raw=raw[:200])
            return []

        validated = []
        for m in metrics_raw:
            if not isinstance(m, dict):
                continue
            if not all(k in m for k in ("label", "value", "source_url", "metric_type")):
                continue
            if m.get("metric_type") not in _VALID_METRIC_TYPES:
                m["metric_type"] = "other"
            validated.append({
                "label": str(m["label"])[:80],
                "value": str(m["value"]),
                "context": str(m.get("context", "")),
                "source_url": str(m["source_url"]),
                "metric_type": m["metric_type"],
            })
        return validated[:20]

    async def _complete(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        await self._store(metrics)

        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="metrics",
                event_type="metrics_ready",
                payload={"metric_count": len(metrics), "metrics": metrics},
            )
        )
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="metrics",
                event_type="agent_completed",
                payload={"agent": "metrics", "metric_count": len(metrics)},
            )
        )

        logger.info(
            "metrics.completed",
            session_id=str(self.session_id),
            metric_count=len(metrics),
        )
        return {"metrics": metrics}

    async def _store(self, metrics: list[dict[str, Any]]) -> None:
        try:
            result = await self._db.execute(
                select(ResearchSession).where(ResearchSession.id == self.session_id)
            )
            session = result.scalar_one_or_none()
            if session is not None:
                session.metrics_json = {"metrics": metrics}
                await self._db.flush()
        except Exception as exc:
            logger.warning("metrics.store_error", error=str(exc))


def _format_sources_block(sources: list[Source]) -> str:
    lines = ["<sources>"]
    for i, s in enumerate(sources, 1):
        lines.append(f'<source index="{i}" url="{s.url}" title="{s.title or s.url}">')
        content = (s.cleaned_content or s.raw_content or "").strip()
        if content:
            lines.append(content[:2000])
        lines.append("</source>")
    lines.append("</sources>")
    return "\n".join(lines)
