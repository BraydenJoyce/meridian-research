"""ChartGalleryAgent: materializes CV chart data into a persistent, SSE-delivered gallery."""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentEvent, EventEmitter, ResearchAgent
from app.models.research_session import ResearchSession

logger = structlog.get_logger(__name__)


class ChartGalleryAgent(ResearchAgent):
    """
    Transforms CvDocumentAgent chart_results into a structured gallery payload.

    No LLM call — pure data transformation. Deduplicates by image_url and pushes
    the full gallery over SSE so the frontend can render charts immediately without
    an additional API call. Stores result in research_sessions.chart_gallery_json.
    Non-fatal.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        emitter: EventEmitter,
        db: AsyncSession,
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="chart_gallery",
                event_type="agent_started",
                payload={"agent": "chart_gallery"},
            )
        )

        chart_results: list[dict[str, Any]] = input_data.get("chart_results", [])
        gallery = self._build_gallery(chart_results)

        await self._store(gallery)

        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="chart_gallery",
                event_type="chart_gallery_ready",
                payload={"chart_count": len(gallery), "gallery": gallery},
            )
        )
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="chart_gallery",
                event_type="agent_completed",
                payload={"agent": "chart_gallery", "chart_count": len(gallery)},
            )
        )

        logger.info(
            "chart_gallery.completed",
            session_id=str(self.session_id),
            chart_count=len(gallery),
        )
        return {"chart_gallery": gallery, "chart_count": len(gallery)}

    def _build_gallery(self, chart_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen_urls: set[str] = set()
        gallery: list[dict[str, Any]] = []

        for item in chart_results:
            if not isinstance(item, dict):
                continue
            image_url = str(item.get("image_url", ""))
            if not image_url or image_url in seen_urls:
                continue
            seen_urls.add(image_url)

            series = item.get("series", [])
            if not isinstance(series, list):
                series = []

            gallery.append({
                "image_url": image_url,
                "source_url": str(item.get("source_url", "")),
                "chart_type": str(item.get("chart_type", "unknown")),
                "title": item.get("title") or None,
                "key_insight": str(item.get("key_insight", "")),
                "series_count": len(series),
                "x_axis": item.get("x_axis") or None,
                "y_axis": item.get("y_axis") or None,
                "series": series,
            })

        return gallery

    async def _store(self, gallery: list[dict[str, Any]]) -> None:
        try:
            result = await self._db.execute(
                select(ResearchSession).where(ResearchSession.id == self.session_id)
            )
            session = result.scalar_one_or_none()
            if session is not None:
                session.chart_gallery_json = {"gallery": gallery, "chart_count": len(gallery)}
                await self._db.flush()
        except Exception as exc:
            logger.warning("chart_gallery.store_error", error=str(exc))
