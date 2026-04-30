"""Tests for research_worker parallel agent orchestration (t-033)."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.research_worker import _merge_results, _run_parallel_agents


class FakeEmitter:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


def _make_fake_agent(result: Any = None, sleep: float = 0.01) -> MagicMock:
    agent = MagicMock()

    async def _run(input_data: dict[str, Any]) -> Any:
        await asyncio.sleep(sleep)
        if isinstance(result, Exception):
            raise result
        return result or {}

    agent.run = _run
    return agent


@pytest.mark.asyncio
async def test_all_agents_run_in_parallel() -> None:
    agents = [
        _make_fake_agent({"chart_results": []}, sleep=0.05),
        _make_fake_agent({"news_count": 3}, sleep=0.05),
        _make_fake_agent({"edgar_count": 1}, sleep=0.05),
    ]
    names = ["cv_document", "news", "edgar"]

    start = asyncio.get_event_loop().time()
    results = await _run_parallel_agents(agents, names, {"question": "test"})
    elapsed = asyncio.get_event_loop().time() - start

    assert len(results) == 3
    assert elapsed < 0.2, f"Parallel execution took too long: {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_one_agent_failure_does_not_abort_session() -> None:
    agents = [
        _make_fake_agent(result=RuntimeError("CV down"), sleep=0.01),
        _make_fake_agent({"news_count": 5}, sleep=0.01),
        _make_fake_agent({"edgar_count": 0}, sleep=0.01),
    ]
    names = ["cv_document", "news", "edgar"]

    results = await _run_parallel_agents(agents, names, {"question": "test"})

    assert isinstance(results[0], RuntimeError)
    assert isinstance(results[1], dict)
    assert results[1]["news_count"] == 5
    assert isinstance(results[2], dict)


@pytest.mark.asyncio
async def test_agent_timeout_is_handled_gracefully() -> None:
    agents = [
        _make_fake_agent({"news_count": 1}, sleep=0.01),
    ]
    names = ["news"]

    with patch("app.workers.research_worker._RESEARCH_TIMEOUT", 0.001):
        results = await _run_parallel_agents(agents, names, {"question": "test"})

    assert results[0] == {}


@pytest.mark.asyncio
async def test_critic_runs_after_writer() -> None:
    from app.workers.research_worker import _run_critic

    emitter = FakeEmitter()
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()

    session_id = uuid.uuid4()

    with patch("app.workers.research_worker.CriticAgent") as mock_critic_cls:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(
            return_value={"quality_score": 0.9, "flagged_claims": []}
        )
        mock_critic_cls.return_value = mock_instance

        result = await _run_critic(
            session_id,
            emitter,
            db,
            {"report_markdown": "## Summary\nContent.", "sources": []},
        )

    assert result["quality_score"] == 0.9
    mock_instance.run.assert_called_once()


def test_orchestration_summary_event_emitted() -> None:
    web_results = {"sources_count": 20, "source_ids": []}
    enrichment_results: list[Any] = [
        {"chart_results": [{"type": "bar"}], "chart_count": 1},
        {"news_count": 5},
        RuntimeError("EDGAR failed"),
    ]

    merged = _merge_results(web_results, enrichment_results)

    meta = merged["_meta"]
    assert "agents_succeeded" in meta
    assert "agents_failed" in meta
    assert meta["agents_failed"] == 1
    assert meta["agents_succeeded"] >= 2
    assert meta["chart_count"] == 1
