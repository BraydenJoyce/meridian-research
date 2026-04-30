"""Tests for StructuredDataAgent (t-031)."""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.structured_data import StructuredDataAgent


class FakeEmitter:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


def _make_agent() -> tuple[StructuredDataAgent, FakeEmitter, AsyncMock]:
    emitter = FakeEmitter()
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    agent = StructuredDataAgent(
        session_id=uuid.uuid4(),
        emitter=emitter,
        db=db,
    )
    return agent, emitter, db


def _make_search_response(ciks: list[str]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    hits = [{"_source": {"entity_id": cik}} for cik in ciks]
    resp.json.return_value = {"hits": {"hits": hits}}
    return resp


def _make_facts_response(company_name: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "entityName": company_name,
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "end": "2024-12-31", "val": 100_000_000},
                            {"form": "10-K", "end": "2023-12-31", "val": 90_000_000},
                        ]
                    }
                }
            }
        },
    }
    return resp


@pytest.mark.asyncio
async def test_structured_data_fetches_xbrl_facts() -> None:
    agent, _emitter, _db = _make_agent()

    search_resp = _make_search_response(["0000320193"])
    facts_resp = _make_facts_response("Apple Inc.")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[search_resp, facts_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.structured_data.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "Apple revenue 2024"})

    assert result["edgar_count"] == 1
    assert "Apple Inc." in result["edgar_companies"]


@pytest.mark.asyncio
async def test_structured_data_stores_source_rows() -> None:
    agent, _emitter, db = _make_agent()

    search_resp = _make_search_response(["0000320193"])
    facts_resp = _make_facts_response("Apple Inc.")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[search_resp, facts_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.structured_data.httpx.AsyncClient", return_value=mock_client):
        await agent.run({"question": "Apple revenue"})

    assert db.add.called
    added = db.add.call_args[0][0]
    assert added.source_type == "edgar"
    assert "Apple Inc." in (added.title or "")


@pytest.mark.asyncio
async def test_structured_data_limits_to_3_companies() -> None:
    agent, _emitter, _db = _make_agent()

    search_resp = _make_search_response(["0000000001", "0000000002", "0000000003", "0000000004"])
    facts_resps = [_make_facts_response(f"Company {i}") for i in range(3)]

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[search_resp, *facts_resps])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.structured_data.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "big tech earnings"})

    assert result["edgar_count"] <= 3
    assert len(result["edgar_companies"]) <= 3


@pytest.mark.asyncio
async def test_structured_data_handles_missing_cik() -> None:
    agent, _emitter, _db = _make_agent()

    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json.return_value = {"hits": {"hits": []}}

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=search_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.structured_data.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "unknown company xyz"})

    assert result["edgar_count"] == 0
    assert result["edgar_companies"] == []


@pytest.mark.asyncio
async def test_structured_data_http_error_is_nonfatal() -> None:

    agent, _emitter, _db = _make_agent()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=Exception("connection timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.structured_data.httpx.AsyncClient", return_value=mock_client):
        result = await agent.run({"question": "test"})

    assert result["edgar_count"] == 0
    assert not isinstance(result, Exception)


@pytest.mark.asyncio
async def test_structured_data_emits_correct_events() -> None:
    agent, emitter, _db = _make_agent()

    search_resp = _make_search_response(["0000320193"])
    facts_resp = _make_facts_response("Apple Inc.")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[search_resp, facts_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agents.structured_data.httpx.AsyncClient", return_value=mock_client):
        await agent.run({"question": "Apple"})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_started" in event_types
    assert "edgar_fetched" in event_types
    assert "agent_completed" in event_types
