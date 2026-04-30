"""NewsAgent: retrieves recent news articles from NewsAPI and GNews (ADR-007)."""
from __future__ import annotations

import uuid
from typing import Any

import httpx
import structlog

from app.agents.base import AgentEvent, EventEmitter, ResearchAgent
from app.models.source import Source

logger = structlog.get_logger(__name__)

_NEWSAPI_URL = "https://newsapi.org/v2/everything"
_GNEWS_URL = "https://gnews.io/api/v4/search"
_PAGE_SIZE = 10


class NewsAgent(ResearchAgent):
    """
    Fetches recent news articles from NewsAPI and GNews concurrently.

    Non-fatal: missing API keys or HTTP errors return empty results and log
    a warning. Never raises AgentFatalError.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        emitter: EventEmitter,
        db: Any,
        newsapi_key: str = "",
        gnews_key: str = "",
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db
        self._newsapi_key = newsapi_key
        self._gnews_key = gnews_key

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="news",
                event_type="agent_started",
                payload={"agent": "news"},
            )
        )

        try:
            source_ids = await self._fetch_and_store(input_data.get("question", ""))
        except Exception as exc:
            logger.warning("news_agent_error", session_id=str(self.session_id), error=str(exc))
            await self.emitter.emit(
                AgentEvent(
                    session_id=self.session_id,
                    agent_type="news",
                    event_type="agent_failed",
                    payload={"agent": "news", "error": str(exc)},
                )
            )
            return {"news_source_ids": [], "news_count": 0}

        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="news",
                event_type="news_fetched",
                payload={"agent": "news", "count": len(source_ids)},
            )
        )
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="news",
                event_type="agent_completed",
                payload={"agent": "news", "news_count": len(source_ids)},
            )
        )
        return {"news_source_ids": source_ids, "news_count": len(source_ids)}

    async def _fetch_and_store(self, question: str) -> list[uuid.UUID]:
        articles: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            import asyncio

            newsapi_task = self._fetch_newsapi(client, question)
            gnews_task = self._fetch_gnews(client, question)
            results = await asyncio.gather(newsapi_task, gnews_task, return_exceptions=True)

        for r in results:
            if isinstance(r, list):
                articles.extend(r)

        seen_urls: set[str] = set()
        unique: list[dict[str, Any]] = []
        for article in articles:
            url = article.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(article)

        source_ids: list[uuid.UUID] = []
        for article in unique:
            source = Source(
                session_id=self.session_id,
                url=article["url"],
                sub_task_index=0,
                title=article.get("title"),
                raw_content=article.get("description") or article.get("content"),
                source_type="news",
            )
            self._db.add(source)
            source_ids.append(source.id)

        if source_ids:
            await self._db.flush()

        return source_ids

    async def _fetch_newsapi(
        self, client: httpx.AsyncClient, question: str
    ) -> list[dict[str, Any]]:
        if not self._newsapi_key:
            logger.warning("news_agent.newsapi_key_missing")
            return []
        try:
            resp = await client.get(
                _NEWSAPI_URL,
                params={
                    "q": question,
                    "pageSize": _PAGE_SIZE,
                    "sortBy": "relevancy",
                    "apiKey": self._newsapi_key,
                },
            )
            if resp.status_code != 200:
                logger.warning("news_agent.newsapi_error", status=resp.status_code)
                return []
            return resp.json().get("articles", [])
        except Exception as exc:
            logger.warning("news_agent.newsapi_exception", error=str(exc))
            return []

    async def _fetch_gnews(
        self, client: httpx.AsyncClient, question: str
    ) -> list[dict[str, Any]]:
        if not self._gnews_key:
            logger.warning("news_agent.gnews_key_missing")
            return []
        try:
            resp = await client.get(
                _GNEWS_URL,
                params={
                    "q": question,
                    "max": _PAGE_SIZE,
                    "lang": "en",
                    "token": self._gnews_key,
                },
            )
            if resp.status_code != 200:
                logger.warning("news_agent.gnews_error", status=resp.status_code)
                return []
            articles = resp.json().get("articles", [])
            for a in articles:
                if "url" not in a and "link" in a:
                    a["url"] = a["link"]
            return articles
        except Exception as exc:
            logger.warning("news_agent.gnews_exception", error=str(exc))
            return []
