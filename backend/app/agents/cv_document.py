"""CV Document Agent: classifies images and extracts chart data via Modal (ADR-005)."""
from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentError, AgentEvent, EventEmitter, ResearchAgent
from app.models.chart_extraction import ChartExtraction
from app.models.source import Source
from app.schemas.cv import ChartResult

logger = structlog.get_logger(__name__)

_IMAGE_URL_PATTERN = re.compile(
    r'(?:<img[^>]+src=["\']([^"\']+\.(png|jpg|jpeg|gif|webp))["\']'
    r'|!\[[^\]]*\]\(([^)]+\.(png|jpg|jpeg|gif|webp))\))',
    re.IGNORECASE,
)
_MAX_IMAGES_PER_SESSION = 50
_STARTUP_WAIT_SECONDS = 10
_CONFIDENCE_THRESHOLD = 0.70
_EXTRACTABLE_CLASSES = frozenset(
    {"bar_chart", "line_chart", "pie_chart", "scatter_plot", "table"}
)


def _extract_image_urls(raw_content: str) -> list[str]:
    """Extract image URLs from raw HTML/Markdown content."""
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
    Extracts structured chart data from document images found in research sources.

    Runs concurrently with WebSearchAgent. After a brief startup wait it queries
    the sources table, extracts image URLs, classifies each via Modal /classify,
    then extracts chart data via Modal /extract-chart for qualifying images.

    CV failure is always AgentError (never AgentFatalError). Sessions with zero
    charts complete normally as text-only reports.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        emitter: EventEmitter,
        db: AsyncSession,
        modal_base_url: str,
        modal_api_secret: str = "",
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db
        self._modal_base_url = modal_base_url.rstrip("/")
        self._headers: dict[str, str] = {}
        if modal_api_secret:
            self._headers["Authorization"] = f"Bearer {modal_api_secret}"

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
            logger.warning(
                "cv_agent_error",
                session_id=str(self.session_id),
                error=str(exc),
            )
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
                payload={
                    "agent": "cv_document",
                    "charts_extracted": len(chart_results),
                },
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

        image_urls = _collect_image_urls(sources)
        if not image_urls:
            logger.info("cv_agent.no_images", session_id=str(self.session_id))
            return []

        semaphore = asyncio.Semaphore(3)
        tasks = [
            self._process_image(image_url, source_url, semaphore)
            for image_url, source_url in image_urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        chart_results: list[ChartResult] = []
        for r in results:
            if isinstance(r, AgentError):
                raise r  # propagate auth / fatal errors
            elif isinstance(r, ChartResult):
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

            if self._modal_base_url == "local":
                return None

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0), headers=self._headers
            ) as client:
                classify_resp = await self._classify(client, image_url, source_url)
                if classify_resp is None:
                    return None

                doc_class, confidence = classify_resp
                await self.emitter.emit(
                    AgentEvent(
                        session_id=self.session_id,
                        agent_type="cv_document",
                        event_type="cv_document_classified",
                        payload={
                            "source_url": source_url,
                            "image_url": image_url,
                            "doc_class": doc_class,
                            "confidence": confidence,
                        },
                    )
                )

                if doc_class not in _EXTRACTABLE_CLASSES or confidence < _CONFIDENCE_THRESHOLD:
                    return None

                chart_result = await self._extract_chart(
                    client, image_url, source_url, doc_class
                )
                if chart_result is None:
                    return None

                await self._store_extraction(chart_result, confidence)
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

    async def _classify(
        self,
        client: httpx.AsyncClient,
        image_url: str,
        source_url: str,
    ) -> tuple[str, float] | None:
        try:
            resp = await client.post(
                f"{self._modal_base_url}/classify",
                json={"image_url": image_url, "session_id": str(self.session_id)},
            )
            if resp.status_code == 401:
                raise AgentError("Modal authentication failed (401)")
            if resp.status_code >= 500:
                logger.warning(
                    "cv_classify_server_error", image_url=image_url, status=resp.status_code
                )
                return None
            if resp.status_code >= 400:
                logger.debug("cv_classify_skip", image_url=image_url, status=resp.status_code)
                return None
            data = resp.json()
            return data["doc_class"], float(data["confidence"])
        except AgentError:
            raise
        except Exception as exc:
            logger.debug("cv_classify_error", image_url=image_url, error=str(exc))
            return None

    async def _extract_chart(
        self,
        client: httpx.AsyncClient,
        image_url: str,
        source_url: str,
        doc_class: str,
    ) -> ChartResult | None:
        try:
            resp = await client.post(
                f"{self._modal_base_url}/extract-chart",
                json={
                    "image_url": image_url,
                    "session_id": str(self.session_id),
                    "source_url": source_url,
                    "doc_class": doc_class,
                },
            )
            if resp.status_code >= 400:
                logger.debug("cv_extract_error", image_url=image_url, status=resp.status_code)
                return None
            payload = resp.json()
            if payload is None:
                return None
            return ChartResult.model_validate(payload)
        except Exception as exc:
            logger.debug("cv_extract_exception", image_url=image_url, error=str(exc))
            return None

    async def _store_extraction(
        self, chart_result: ChartResult, confidence: float
    ) -> None:
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
            doc_class_confidence=Decimal(str(round(confidence, 4))),
        )
        self._db.add(extraction)
        await self._db.flush()


def _collect_image_urls(sources: list[Source]) -> list[tuple[str, str]]:
    """
    Extract image URLs from source raw_content fields.

    Returns:
        List of (image_url, source_url) pairs, capped at _MAX_IMAGES_PER_SESSION.
    """
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
                    logger.warning(
                        "cv_agent.image_cap_reached",
                        cap=_MAX_IMAGES_PER_SESSION,
                    )
                    return results
    return results
