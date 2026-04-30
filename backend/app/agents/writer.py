import uuid
from typing import Any

import anthropic
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentEvent, AgentFatalError, EventEmitter, ResearchAgent
from app.models.research_session import ResearchSession
from app.models.source import Source
from app.services.chart_formatter import format_charts_section

logger = structlog.get_logger(__name__)

WRITER_MODEL = "claude-3-5-sonnet-20241022"
MIN_QUALITY_SCORE = 0.4
MAX_SOURCES_CONTEXT = 30

SYSTEM_PROMPT = (
    "You are a professional market intelligence analyst. "
    "Your task is to synthesize research sources into a structured markdown report. "
    "Requirements:\n"
    "- Start with an ## Executive Summary section\n"
    "- Include one ## section per research sub-task\n"
    "- End with a ## Conclusion section\n"
    "- Every factual claim must have an inline citation: [Source Title](url)\n"
    "- Write in formal, concise business language\n"
    "- Use bullet points for key findings within each section\n"
    "- Minimum 3 citations across the report\n"
    "- When chart data is provided in the '## Data from Charts' section, reference "
    "specific data points from charts in your analysis and cite the chart's source_url "
    "using the standard inline citation format [Source Title](url)."
)


class WriterAgent(ResearchAgent):
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
        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="writer",
            event_type="agent_started",
            payload={"agent": "writer"},
        ))

        sources = await self._load_sources()
        if not sources:
            await self._fail("No sources available for report generation")
            raise AgentFatalError("No scored sources found for session")

        chart_results: list[dict[str, Any]] = input_data.get("chart_results", [])
        markdown = await self._generate_report(
            sources, input_data.get("question", ""), chart_results
        )

        if not markdown or len(markdown.strip()) < 100:
            await self._fail("Generated report is too short or empty")
            raise AgentFatalError("Writer produced an empty or too-short report")

        await self._save_report(markdown)

        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="writer",
            event_type="report_complete",
            payload={
                "agent": "writer",
                "markdown": markdown,
                "source_count": len(sources),
            },
        ))

        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="writer",
            event_type="agent_completed",
            payload={"agent": "writer", "source_count": len(sources)},
        ))

        logger.info(
            "writer.completed",
            session_id=str(self.session_id),
            source_count=len(sources),
            report_length=len(markdown),
        )
        return {"report_markdown": markdown}

    async def _load_sources(self) -> list[Source]:
        result = await self._db.execute(
            select(Source)
            .where(Source.session_id == self.session_id)
            .order_by(Source.sub_task_index)
        )
        all_sources = list(result.scalars().all())
        scored = [
            s for s in all_sources
            if s.relevance_score is not None and float(s.relevance_score) > MIN_QUALITY_SCORE
        ]
        if not scored:
            scored = all_sources
        return scored[:MAX_SOURCES_CONTEXT]

    async def _generate_report(
        self,
        sources: list[Source],
        question: str,
        chart_results: list[dict[str, Any]] | None = None,
    ) -> str:
        sources_block = _format_sources_block(sources)
        chart_block = format_charts_section(chart_results or [])

        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": sources_block,
                "cache_control": {"type": "ephemeral"},
            },
        ]
        if chart_block:
            user_content.append({"type": "text", "text": chart_block})
        user_content.append(
            {
                "type": "text",
                "text": (
                    f"Research question: {question}\n\n"
                    "Write the full markdown intelligence report now."
                ),
            }
        )

        message = await self._client.messages.create(
            model=WRITER_MODEL,
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

        for block in message.content:
            if hasattr(block, "type") and block.type == "text":
                return str(block.text)
        return ""

    async def _save_report(self, markdown: str) -> None:
        result = await self._db.execute(
            select(ResearchSession).where(ResearchSession.id == self.session_id)
        )
        session = result.scalar_one_or_none()
        if session is not None:
            session.status = "completed"
            session.report_markdown = markdown
            await self._db.flush()

    async def _fail(self, reason: str) -> None:
        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="writer",
            event_type="agent_failed",
            payload={"agent": "writer", "error": reason},
        ))


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
