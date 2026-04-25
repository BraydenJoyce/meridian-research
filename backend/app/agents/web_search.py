import asyncio
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentError, AgentEvent, AgentFatalError, EventEmitter, ResearchAgent
from app.core.config import settings
from app.models.source import Source

logger = structlog.get_logger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
MAX_CONCURRENT_FETCHES = 5
MIN_TOTAL_SOURCES = 20
REQUEST_TIMEOUT = 10.0


class WebSearchAgent(ResearchAgent):
    def __init__(
        self,
        session_id: uuid.UUID,
        emitter: EventEmitter,
        db: AsyncSession,
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        sub_tasks: list[str] = input_data["sub_tasks"]

        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="web_search",
            event_type="agent_started",
            payload={"agent": "web_search", "sub_task_count": len(sub_tasks)},
        ))

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
        source_ids: list[uuid.UUID] = []

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
            tasks = [
                self._search_sub_task(http, semaphore, idx, query, source_ids)
                for idx, query in enumerate(sub_tasks)
            ]
            await asyncio.gather(*tasks)

        await self._db.flush()

        if len(source_ids) < MIN_TOTAL_SOURCES:
            await self.emitter.emit(AgentEvent(
                session_id=self.session_id,
                agent_type="web_search",
                event_type="agent_failed",
                payload={
                    "agent": "web_search",
                    "error": f"Only {len(source_ids)} sources retrieved",
                },
            ))
            raise AgentFatalError(
                f"Retrieved only {len(source_ids)} sources; minimum is {MIN_TOTAL_SOURCES}"
            )

        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="web_search",
            event_type="agent_completed",
            payload={"agent": "web_search", "total_sources": len(source_ids)},
        ))

        logger.info(
            "web_search.completed",
            session_id=str(self.session_id),
            source_count=len(source_ids),
        )
        return {"source_ids": source_ids, "source_count": len(source_ids)}

    async def _search_sub_task(
        self,
        http: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        idx: int,
        query: str,
        source_ids: list[uuid.UUID],
    ) -> None:
        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="web_search",
            event_type="sub_task_started",
            payload={"sub_task_index": idx, "query": query},
        ))

        try:
            async with semaphore:
                resp = await http.post(
                    TAVILY_URL,
                    headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
                    json={
                        "query": query,
                        "max_results": 10,
                        "include_raw_content": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results: list[dict[str, Any]] = data.get("results", [])
            sub_task_source_ids = await self._store_sources(idx, results, source_ids)

            await self.emitter.emit(AgentEvent(
                session_id=self.session_id,
                agent_type="web_search",
                event_type="sub_task_completed",
                payload={
                    "sub_task_index": idx,
                    "source_count": len(sub_task_source_ids),
                    "status": "ok",
                    "error": None,
                },
            ))

        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            error_msg = str(exc)
            logger.warning("web_search.sub_task_failed", idx=idx, error=error_msg)
            await self.emitter.emit(AgentEvent(
                session_id=self.session_id,
                agent_type="web_search",
                event_type="sub_task_completed",
                payload={
                    "sub_task_index": idx,
                    "source_count": 0,
                    "status": "failed",
                    "error": error_msg,
                },
            ))
            raise AgentError(f"Sub-task {idx} failed: {error_msg}") from exc

    async def _store_sources(
        self,
        sub_task_index: int,
        results: list[dict[str, Any]],
        source_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        new_ids: list[uuid.UUID] = []
        for result in results:
            url: str = result.get("url", "")
            if not url:
                continue

            source = Source(
                session_id=self.session_id,
                url=url,
                title=result.get("title"),
                domain=_extract_domain(url),
                sub_task_index=sub_task_index,
                raw_content=result.get("raw_content") or result.get("content"),
                fetched_at=None,
            )
            self._db.add(source)
            new_ids.append(source.id)
            source_ids.append(source.id)

            await self.emitter.emit(AgentEvent(
                session_id=self.session_id,
                agent_type="web_search",
                event_type="source_fetched",
                payload={"source_id": str(source.id), "url": url, "title": source.title},
            ))

        return new_ids


def _extract_domain(url: str) -> str | None:
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None
