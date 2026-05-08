"""CV Document Agent: classify images and extract chart data via Claude Vision."""
from __future__ import annotations

import asyncio
import base64
import json
import re
import uuid
from decimal import Decimal
from typing import Any

import anthropic
import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentError, AgentEvent, EventEmitter, ResearchAgent
from app.core.config import get_settings
from app.models.chart_extraction import ChartExtraction
from app.models.source import Source
from app.schemas.cv import ChartResult

logger = structlog.get_logger(__name__)

_IMAGE_URL_PATTERN = re.compile(
    r'(?:<img[^>]+src=["\']([^"\']+\.(png|jpg|jpeg|gif|webp))["\']'
    r'|!\[[^\]]*\]\(([^)]+\.(png|jpg|jpeg|gif|webp))\))',
    re.IGNORECASE,
)
_MAX_IMAGES_PER_SESSION = 25
_STARTUP_WAIT_SECONDS = 10
_CONCURRENCY = 3
_VALID_CHART_TYPES = frozenset(
    {"bar_chart", "line_chart", "pie_chart", "scatter_plot", "table"}
)

_SYSTEM_PROMPT = (
    "You are a data extraction assistant specializing in charts and data visualizations.\n\n"
    "Examine the image and determine whether it is a meaningful data visualization "
    "(bar chart, line chart, pie chart, scatter plot, or data table with numeric values).\n\n"
    "If it IS a chart or data table, respond with this JSON:\n"
    "{\n"
    '  "is_chart": true,\n'
    '  "chart_type": "<bar_chart|line_chart|pie_chart|scatter_plot|table>",\n'
    '  "title": "<chart title or null>",\n'
    '  "x_axis": "<x-axis label or null>",\n'
    '  "y_axis": "<y-axis label or null>",\n'
    '  "series": [\n'
    '    {"name": "<series name>", "data_points": [{"label": "<x value>", "value": <number or "unreadable">}]}\n'
    "  ],\n"
    '  "key_insight": "<1-2 sentence summary of the most important finding>"\n'
    "}\n\n"
    "If it is NOT a chart (logo, photo, icon, banner, decorative image, "
    "or infographic without extractable numeric data), respond with:\n"
    '{"is_chart": false}\n\n'
    "Rules:\n"
    "- pie chart: x_axis and y_axis must be null; each slice = one DataPoint "
    "(label=slice name, value=percentage as float)\n"
    "- table: x_axis and y_axis must be null; each column = one series\n"
    "- key_insight: always required when is_chart=true; never empty\n"
    "- Output ONLY the JSON object, no markdown fences, no explanation"
)


def _detect_media_type(image_bytes: bytes) -> str:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"


def _extract_image_urls(raw_content: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in _IMAGE_URL_PATTERN.finditer(raw_content):
        url = match.group(1) or match.group(3)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


class CvDocumentAgent(ResearchAgent):
    """
    Extracts structured chart data from images found in research sources.

    Uses Claude Vision to classify and extract in a single call — no external
    ML server required. Runs concurrently with other enrichment agents.
    Non-fatal: sessions with zero charts complete normally as text-only reports.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        emitter: EventEmitter,
        db: AsyncSession,
        # Legacy params kept for call-site compatibility; no longer used
        modal_base_url: str = "local",
        modal_api_secret: str = "",
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db
        self._client = anthropic.AsyncAnthropic()

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="cv_document",
                event_type="agent_started",
                payload={"agent": "cv_document"},
            )
        )

        try:
            chart_results = await self._process_session()
        except Exception as exc:
            logger.warning("cv_agent_error", session_id=str(self.session_id), error=str(exc))
            await self.emitter.emit(
                AgentEvent(
                    session_id=self.session_id,
                    agent_type="cv_document",
                    event_type="agent_failed",
                    payload={"agent": "cv_document", "error": str(exc)},
                )
            )
            raise AgentError(str(exc)) from exc

        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="cv_document",
                event_type="agent_completed",
                payload={"agent": "cv_document", "charts_extracted": len(chart_results)},
            )
        )
        return {
            "chart_results": [c.model_dump() for c in chart_results],
            "chart_count": len(chart_results),
        }

    async def _process_session(self) -> list[ChartResult]:
        await asyncio.sleep(_STARTUP_WAIT_SECONDS)

        sources = await self._load_sources()
        if not sources:
            logger.info("cv_agent.no_sources", session_id=str(self.session_id))
            return []

        image_pairs = _collect_image_urls(sources)
        if not image_pairs:
            logger.info("cv_agent.no_images", session_id=str(self.session_id))
            return []

        semaphore = asyncio.Semaphore(_CONCURRENCY)
        tasks = [
            self._process_image(image_url, source_url, semaphore)
            for image_url, source_url in image_pairs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        chart_results: list[ChartResult] = []
        for r in results:
            if isinstance(r, ChartResult):
                chart_results.append(r)
            elif isinstance(r, Exception):
                logger.debug("cv_agent.image_failed", error=str(r))

        return chart_results

    async def _load_sources(self) -> list[Source]:
        result = await self._db.execute(
            select(Source).where(
                Source.session_id == self.session_id,
                Source.raw_content.isnot(None),
            )
        )
        return list(result.scalars().all())

    async def _process_image(
        self,
        image_url: str,
        source_url: str,
        semaphore: asyncio.Semaphore,
    ) -> ChartResult | None:
        async with semaphore:
            await self.emitter.emit(
                AgentEvent(
                    session_id=self.session_id,
                    agent_type="cv_document",
                    event_type="cv_document_started",
                    payload={"source_url": source_url, "image_url": image_url},
                )
            )

            image_bytes = await _fetch_image(image_url)
            if image_bytes is None:
                return None

            chart_result = await self._classify_and_extract(
                image_bytes, image_url, source_url
            )
            if chart_result is None:
                return None

            await self._store_extraction(chart_result)
            await self.emitter.emit(
                AgentEvent(
                    session_id=self.session_id,
                    agent_type="cv_document",
                    event_type="cv_chart_extracted",
                    payload={
                        "source_url": source_url,
                        "image_url": image_url,
                        "chart_type": chart_result.chart_type,
                    },
                )
            )
            return chart_result

    async def _classify_and_extract(
        self,
        image_bytes: bytes,
        image_url: str,
        source_url: str,
    ) -> ChartResult | None:
        media_type = _detect_media_type(image_bytes)
        image_b64 = base64.standard_b64encode(image_bytes).decode()

        for attempt in range(2):
            suffix = (
                "" if attempt == 0
                else "\n\nYour previous response was not valid JSON. Return ONLY the JSON object."
            )
            try:
                response = await self._client.messages.create(
                    model=get_settings().anthropic_writer_model,
                    max_tokens=2048,
                    system=[{"type": "text", "text": _SYSTEM_PROMPT,
                              "cache_control": {"type": "ephemeral"}}],
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Examine this image. Is it a data chart or table? "
                                    "Follow the system prompt instructions." + suffix
                                ),
                            },
                        ],
                    }],
                )
            except Exception as exc:
                logger.debug("cv_vision_api_error", image_url=image_url, error=str(exc))
                return None

            raw = response.content[0].text if response.content else ""
            result = _parse_vision_response(raw, image_url, source_url)
            if result is not None:
                return result

        return None

    async def _store_extraction(self, chart_result: ChartResult) -> None:
        extraction = ChartExtraction(
            session_id=self.session_id,
            image_url=chart_result.image_url,
            source_url=chart_result.source_url,
            chart_type=chart_result.chart_type,
            key_insight=chart_result.key_insight,
            series=[s.model_dump() for s in chart_result.series],
            title=chart_result.title,
            x_axis=chart_result.x_axis,
            y_axis=chart_result.y_axis,
            doc_class_confidence=Decimal("1.0"),
        )
        self._db.add(extraction)
        await self._db.flush()


def _parse_vision_response(
    raw: str, image_url: str, source_url: str
) -> ChartResult | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        data: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    if not data.get("is_chart"):
        return None

    chart_type = data.get("chart_type", "")
    if chart_type not in _VALID_CHART_TYPES:
        return None

    data["image_url"] = image_url
    data["source_url"] = source_url
    try:
        return ChartResult.model_validate(data)
    except Exception:
        return None


async def _fetch_image(image_url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(image_url, follow_redirects=True)
            resp.raise_for_status()
            if len(resp.content) > 5 * 1024 * 1024:
                return None
            if len(resp.content) < 1024:
                return None
            return resp.content
    except Exception as exc:
        logger.debug("cv_image_fetch_failed", image_url=image_url, error=str(exc))
        return None


def _collect_image_urls(sources: list[Source]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    results: list[tuple[str, str]] = []
    for source in sources:
        if not source.raw_content:
            continue
        for img_url in _extract_image_urls(source.raw_content):
            if img_url not in seen:
                seen.add(img_url)
                results.append((img_url, source.url))
                if len(results) >= _MAX_IMAGES_PER_SESSION:
                    logger.info("cv_agent.image_cap_reached", cap=_MAX_IMAGES_PER_SESSION)
                    return results
    return results
