import asyncio
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentEvent, AgentFatalError, EventEmitter, ResearchAgent
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
        tavily_api_key: str | None = None,
        results_per_subtask: int = 10,
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db
        self._tavily_api_key = (
            tavily_api_key if tavily_api_key is not None else settings.tavily_api_key
        )
        self._results_per_subtask = results_per_subtask

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
        seen_urls: set[str] = set()

        for idx, query in enumerate(sub_tasks):
            await self.emitter.emit(AgentEvent(
                session_id=self.session_id,
                agent_type="web_search",
                event_type="sub_task_started",
                payload={"sub_task_index": idx, "query": query},
            ))

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
            tasks = [
                self._search_sub_task(http, semaphore, query)
                for idx, query in enumerate(sub_tasks)
            ]
            task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(task_results):
            if isinstance(result, Exception):
                error_msg = str(result)
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
                continue

            sub_task_source_ids = await self._store_sources(
                idx, result, source_ids, seen_urls
            )
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
        query: str,
    ) -> list[dict[str, Any]]:
        async with semaphore:
            resp = await http.post(
                TAVILY_URL,
                headers={"Authorization": f"Bearer {self._tavily_api_key}"},
                json={
                    "query": query,
                    "max_results": self._results_per_subtask,
                    "include_raw_content": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return list(data.get("results", []))

    async def _store_sources(
        self,
        sub_task_index: int,
        results: list[dict[str, Any]],
        source_ids: list[uuid.UUID],
        seen_urls: set[str],
    ) -> list[uuid.UUID]:
        new_ids: list[uuid.UUID] = []
        for result in results:
            url: str = result.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

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
