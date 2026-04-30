"""Tests for NewsAgent (t-030)."""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.news import NewsAgent


class FakeEmitter:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


def _make_agent(
    newsapi_key: str = "test-newsapi",
    gnews_key: str = "test-gnews",
) -> tuple[NewsAgent, FakeEmitter, AsyncMock]:
    emitter = FakeEmitter()
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    agent = NewsAgent(
        session_id=uuid.uuid4(),
        emitter=emitter,
        db=db,
        newsapi_key=newsapi_key,
        gnews_key=gnews_key,
    )
    return agent, emitter, db


def _make_newsapi_response(articles: list[dict[str, Any]]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"articles": articles}
    return resp


def _make_gnews_response(articles: list[dict[str, Any]]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"articles": articles}
    return resp


@pytest.mark.asyncio
async def test_news_agent_returns_articles_from_both_apis() -> None:
    agent, _emitter, _db = _make_agent()

    newsapi_resp = _make_newsapi_response([
        {"url": "https://example.com/a1", "title": "Article 1", "description": "desc 1"},
    ])
    gnews_resp = _make_gnews_response([
        {"url": "https://gnews.com/a2", "title": "Article 2", "description": "desc 2"},
    ])

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[newsapi_resp, gnews_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.news.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "AI market trends"})

    assert result["news_count"] == 2
    assert len(result["news_source_ids"]) == 2


@pytest.mark.asyncio
async def test_news_agent_deduplicates_by_url() -> None:
    agent, _emitter, _db = _make_agent()

    shared_url = "https://example.com/shared"
    newsapi_resp = _make_newsapi_response([
        {"url": shared_url, "title": "Article", "description": "desc"},
    ])
    gnews_resp = _make_gnews_response([
        {"url": shared_url, "title": "Same Article", "description": "desc"},
        {"url": "https://gnews.com/unique", "title": "Unique", "description": "unique"},
    ])

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[newsapi_resp, gnews_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.news.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "test"})

    assert result["news_count"] == 2  # shared_url counted once + unique


@pytest.mark.asyncio
async def test_news_agent_missing_newsapi_key_returns_empty_from_that_source() -> None:
    agent, _emitter, _db = _make_agent(newsapi_key="")

    gnews_resp = _make_gnews_response([
        {"url": "https://gnews.com/a1", "title": "G1", "description": "d1"},
    ])

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=gnews_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.news.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "test"})

    assert result["news_count"] == 1  # only gnews result


@pytest.mark.asyncio
async def test_news_agent_missing_gnews_key_returns_empty_from_that_source() -> None:
    agent, _emitter, _db = _make_agent(gnews_key="")

    newsapi_resp = _make_newsapi_response([
        {"url": "https://newsapi.com/a1", "title": "N1", "description": "d1"},
    ])

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=newsapi_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.news.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "test"})

    assert result["news_count"] == 1


@pytest.mark.asyncio
async def test_news_agent_api_error_does_not_raise_fatal() -> None:

    agent, emitter, _db = _make_agent()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.news.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "test"})

    assert result["news_count"] == 0
    assert result["news_source_ids"] == []
    event_types = [e.event_type for e in emitter.events]
    assert "agent_started" in event_types
    assert "agent_completed" in event_types


@pytest.mark.asyncio
async def test_news_agent_emits_correct_events() -> None:
    agent, emitter, _db = _make_agent()

    newsapi_resp = _make_newsapi_response([
        {"url": "https://example.com/n1", "title": "N1", "description": "d"},
    ])
    gnews_resp = _make_gnews_response([])

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[newsapi_resp, gnews_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.news.httpx.AsyncClient", return_value=mock_client):
        await agent.run({"question": "test"})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_started" in event_types
    assert "news_fetched" in event_types
    assert "agent_completed" in event_types
