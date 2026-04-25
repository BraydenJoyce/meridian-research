import re
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentEvent, AgentFatalError, EventEmitter
from app.agents.writer import WriterAgent

SESSION_ID = uuid.uuid4()

SAMPLE_MARKDOWN = """## Executive Summary

The CRM market is growing rapidly with [Salesforce](https://reuters.com/a1) dominating
with $35B ARR. [HubSpot Corp](https://bloomberg.com/a2) expands enterprise segment.
[Gartner analysis](https://gartner.com/a3) projects 14.5% CAGR through 2028.

## Market Share Analysis

- Salesforce holds 23% global CRM market share per [Salesforce report](https://reuters.com/a1)
- Growth driven by AI features

## AI CRM Trends

- [HubSpot Corp](https://bloomberg.com/a2) launched AI features in Q1 2026

## Conclusion

The CRM market consolidates around AI-powered platforms.
"""


class FakeEmitter(EventEmitter):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[AgentEvent] = []

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


def make_fake_source(
    idx: int,
    relevance: float = 0.7,
    url: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.session_id = SESSION_ID
    s.url = url or f"https://example{idx}.com/article-{idx}"
    s.title = f"Article {idx}"
    s.domain = f"example{idx}.com"
    s.sub_task_index = idx % 3
    s.raw_content = f"Content {idx} with Salesforce Inc and Microsoft Corporation mentioned."
    s.cleaned_content = None
    s.relevance_score = Decimal(str(relevance))
    return s


def make_mock_message(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


@pytest.fixture
def emitter() -> FakeEmitter:
    return FakeEmitter()


@pytest.fixture
def mock_db() -> AsyncMock:
    sources = [make_fake_source(i) for i in range(5)]

    session_mock = MagicMock()
    session_mock.id = SESSION_ID
    session_mock.status = "running"
    session_mock.report_markdown = None

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    scalars_sources = MagicMock()
    scalars_sources.all.return_value = sources

    scalars_session = MagicMock()
    scalars_session.scalar_one_or_none.return_value = session_mock

    results: list[Any] = []

    async def fake_execute(*args: Any, **kwargs: Any) -> Any:
        if results:
            return results.pop(0)
        r = MagicMock()
        r.scalars.return_value = scalars_sources
        r.scalar_one_or_none.return_value = session_mock
        return r

    db.execute = fake_execute
    return db


@pytest.fixture
def agent(emitter: FakeEmitter, mock_db: AsyncMock) -> WriterAgent:
    return WriterAgent(session_id=SESSION_ID, emitter=emitter, db=mock_db)


@pytest.mark.asyncio
async def test_writer_returns_markdown(
    agent: WriterAgent, emitter: FakeEmitter
) -> None:
    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_message(SAMPLE_MARKDOWN)
        result = await agent.run({"question": "CRM market 2026", "session_id": SESSION_ID})

    assert "report_markdown" in result
    assert len(result["report_markdown"]) > 100


@pytest.mark.asyncio
async def test_writer_report_has_inline_citations(
    agent: WriterAgent,
) -> None:
    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_message(SAMPLE_MARKDOWN)
        result = await agent.run({"question": "CRM market 2026", "session_id": SESSION_ID})

    citations = re.findall(r"\[.+?\]\(https?://.+?\)", result["report_markdown"])
    assert len(citations) >= 3


@pytest.mark.asyncio
async def test_writer_emits_agent_started_completed_report_complete(
    agent: WriterAgent, emitter: FakeEmitter
) -> None:
    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_message(SAMPLE_MARKDOWN)
        await agent.run({"question": "CRM market 2026", "session_id": SESSION_ID})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_started" in event_types
    assert "agent_completed" in event_types
    assert "report_complete" in event_types


@pytest.mark.asyncio
async def test_writer_uses_cache_control(
    agent: WriterAgent,
) -> None:
    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_message(SAMPLE_MARKDOWN)
        await agent.run({"question": "CRM market 2026", "session_id": SESSION_ID})

    call_kwargs = mock_create.call_args[1]
    system_blocks = call_kwargs["system"]
    assert isinstance(system_blocks, list)
    assert any(
        block.get("cache_control", {}).get("type") == "ephemeral"
        for block in system_blocks
    )
    messages = call_kwargs["messages"]
    user_content = messages[0]["content"]
    assert any(
        block.get("cache_control", {}).get("type") == "ephemeral"
        for block in user_content
        if isinstance(block, dict)
    )


@pytest.mark.asyncio
async def test_writer_raises_fatal_error_on_empty_report(
    agent: WriterAgent,
) -> None:
    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_message("")
        with pytest.raises(AgentFatalError):
            await agent.run({"question": "CRM market 2026", "session_id": SESSION_ID})


@pytest.mark.asyncio
async def test_writer_emits_agent_failed_on_error(
    agent: WriterAgent, emitter: FakeEmitter
) -> None:
    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_message("")
        with pytest.raises(AgentFatalError):
            await agent.run({"question": "CRM market 2026", "session_id": SESSION_ID})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_failed" in event_types
