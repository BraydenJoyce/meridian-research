"""Tests for CriticAgent (t-032)."""
from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.critic import CriticAgent


class FakeEmitter:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


def _make_agent() -> tuple[CriticAgent, FakeEmitter, AsyncMock]:
    emitter = FakeEmitter()
    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.scalar_one_or_none = MagicMock(return_value=None)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()
    agent = CriticAgent(
        session_id=uuid.uuid4(),
        emitter=emitter,
        db=db,
    )
    return agent, emitter, db


def _make_claude_response(quality_score: float, flagged: list[dict[str, str]]) -> MagicMock:
    payload = json.dumps({"quality_score": quality_score, "flagged_claims": flagged})
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = payload
    msg = MagicMock()
    msg.content = [content_block]
    return msg


@pytest.mark.asyncio
async def test_critic_returns_quality_score_and_flagged_claims() -> None:
    agent, _emitter, _db = _make_agent()

    fake_response = _make_claude_response(
        0.75,
        [{"claim": "Revenue grew 10%", "reason": "No citation provided"}],
    )
    agent._client = MagicMock()
    agent._client.messages = MagicMock()
    agent._client.messages.create = AsyncMock(return_value=fake_response)

    result = await agent.run({
        "report_markdown": "## Summary\nRevenue grew 10%. [Source](https://example.com)",
        "sources": [{"url": "https://example.com", "title": "Test", "content": "content"}],
    })

    assert result["quality_score"] == 0.75
    assert len(result["flagged_claims"]) == 1
    assert result["flagged_claims"][0]["claim"] == "Revenue grew 10%"


@pytest.mark.asyncio
async def test_critic_handles_json_parse_error_gracefully() -> None:
    agent, _emitter, _db = _make_agent()

    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = "not valid json at all {{{"
    msg = MagicMock()
    msg.content = [content_block]
    agent._client = MagicMock()
    agent._client.messages = MagicMock()
    agent._client.messages.create = AsyncMock(return_value=msg)

    result = await agent.run({
        "report_markdown": "## Summary\nSome content here.",
        "sources": [],
    })

    assert result["quality_score"] == 1.0
    assert result["flagged_claims"] == []


@pytest.mark.asyncio
async def test_critic_emits_correct_events() -> None:
    agent, emitter, _db = _make_agent()

    fake_response = _make_claude_response(0.9, [])
    agent._client = MagicMock()
    agent._client.messages = MagicMock()
    agent._client.messages.create = AsyncMock(return_value=fake_response)

    await agent.run({"report_markdown": "## Summary\nContent.", "sources": []})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_started" in event_types
    assert "report_critique" in event_types
    assert "agent_completed" in event_types


@pytest.mark.asyncio
async def test_critic_stores_critique_in_session() -> None:
    agent, _emitter, db = _make_agent()

    session_mock = MagicMock()
    session_mock.critique_json = None
    db.execute.return_value.scalar_one_or_none = MagicMock(return_value=session_mock)

    fake_response = _make_claude_response(0.8, [])
    agent._client = MagicMock()
    agent._client.messages = MagicMock()
    agent._client.messages.create = AsyncMock(return_value=fake_response)

    await agent.run({"report_markdown": "## Summary\nContent.", "sources": []})

    assert session_mock.critique_json is not None
    assert "quality_score" in session_mock.critique_json


@pytest.mark.asyncio
async def test_critic_api_error_is_nonfatal() -> None:

    agent, emitter, _db = _make_agent()
    agent._client = MagicMock()
    agent._client.messages = MagicMock()
    agent._client.messages.create = AsyncMock(side_effect=Exception("API unreachable"))

    result = await agent.run({"report_markdown": "## Summary\nContent.", "sources": []})

    assert result["quality_score"] == 1.0
    assert result["flagged_claims"] == []
    event_types = [e.event_type for e in emitter.events]
    assert "agent_completed" in event_types


@pytest.mark.asyncio
async def test_critic_quality_score_in_range() -> None:
    agent, _emitter, _db = _make_agent()

    fake_response = _make_claude_response(99.5, [])
    agent._client = MagicMock()
    agent._client.messages = MagicMock()
    agent._client.messages.create = AsyncMock(return_value=fake_response)

    result = await agent.run({"report_markdown": "## Summary\nContent.", "sources": []})

    assert 0.0 <= result["quality_score"] <= 1.0
