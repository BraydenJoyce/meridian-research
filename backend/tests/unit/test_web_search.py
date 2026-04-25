import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentEvent, AgentFatalError, EventEmitter
from app.agents.web_search import WebSearchAgent

SESSION_ID = uuid.uuid4()

SUB_TASKS = [
    "Salesforce CRM market share 2026",
    "HubSpot enterprise adoption trends",
    "AI CRM features competitive analysis",
]


def make_tavily_result(n: int, idx: int = 0) -> list[dict[str, Any]]:
    return [
        {
            "url": f"https://example{idx}.com/article-{i}",
            "title": f"Article {i} sub-task {idx}",
            "content": f"Content for article {i}",
            "raw_content": f"Raw content for article {i} with enough text to be useful",
        }
        for i in range(n)
    ]


class FakeEmitter(EventEmitter):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[AgentEvent] = []

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


@pytest.fixture
def emitter() -> FakeEmitter:
    return FakeEmitter()


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def agent(emitter: FakeEmitter, mock_db: AsyncMock) -> WebSearchAgent:
    return WebSearchAgent(session_id=SESSION_ID, emitter=emitter, db=mock_db)


def make_mock_http_response(results: list[dict[str, Any]]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"results": results}
    return resp


@pytest.mark.asyncio
async def test_web_search_stores_sources_and_returns_ids(
    agent: WebSearchAgent, emitter: FakeEmitter
) -> None:
    results_per_task = 8
    mock_resp = make_mock_http_response(make_tavily_result(results_per_task))

    with patch("app.agents.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await agent.run({"sub_tasks": SUB_TASKS, "session_id": SESSION_ID})

    assert "source_ids" in result
    assert result["source_count"] == results_per_task * len(SUB_TASKS)
    assert len(result["source_ids"]) == results_per_task * len(SUB_TASKS)


@pytest.mark.asyncio
async def test_web_search_raises_fatal_error_when_too_few_sources(
    agent: WebSearchAgent,
) -> None:
    mock_resp = make_mock_http_response(make_tavily_result(2))

    with patch("app.agents.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(AgentFatalError, match="minimum is 20"):
            await agent.run({"sub_tasks": SUB_TASKS, "session_id": SESSION_ID})


@pytest.mark.asyncio
async def test_web_search_emits_agent_started_and_completed(
    agent: WebSearchAgent, emitter: FakeEmitter
) -> None:
    mock_resp = make_mock_http_response(make_tavily_result(8))

    with patch("app.agents.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        await agent.run({"sub_tasks": SUB_TASKS, "session_id": SESSION_ID})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_started" in event_types
    assert "agent_completed" in event_types
    assert "source_fetched" in event_types
    assert "sub_task_started" in event_types
    assert "sub_task_completed" in event_types


@pytest.mark.asyncio
async def test_web_search_respects_semaphore_concurrency(
    agent: WebSearchAgent,
) -> None:
    """Verify that concurrent calls are bounded by MAX_CONCURRENT_FETCHES."""
    call_count = 0
    max_concurrent = 0
    active = 0
    import asyncio

    async def fake_post(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal call_count, max_concurrent, active
        active += 1
        max_concurrent = max(max_concurrent, active)
        call_count += 1
        await asyncio.sleep(0.01)
        active -= 1
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"results": make_tavily_result(8, call_count)}
        return resp

    with patch("app.agents.web_search.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = fake_post
        mock_client_cls.return_value = mock_client

        await agent.run({"sub_tasks": SUB_TASKS, "session_id": SESSION_ID})

    from app.agents.web_search import MAX_CONCURRENT_FETCHES
    assert max_concurrent <= MAX_CONCURRENT_FETCHES
