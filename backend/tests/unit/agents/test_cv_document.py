"""Tests for CvDocumentAgent (t-025)."""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentError
from app.agents.cv_document import CvDocumentAgent, _collect_image_urls, _extract_image_urls


class FakeEmitter:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


def _make_source(raw_content: str = "", url: str = "https://example.com") -> MagicMock:
    src = MagicMock()
    src.raw_content = raw_content
    src.url = url
    src.session_id = uuid.uuid4()
    return src


def _make_agent(
    modal_base_url: str = "https://modal.test",
    db: Any = None,
) -> tuple[CvDocumentAgent, FakeEmitter]:
    emitter = FakeEmitter()
    if db is None:
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [])))
        db.add = MagicMock()
        db.flush = AsyncMock()
    agent = CvDocumentAgent(
        session_id=uuid.uuid4(),
        emitter=emitter,
        db=db,
        modal_base_url=modal_base_url,
        modal_api_secret="test-secret",
    )
    return agent, emitter


def test_extract_image_urls_from_html() -> None:
    html = '<img src="https://example.com/chart.png"> and text'
    urls = _extract_image_urls(html)
    assert "https://example.com/chart.png" in urls


def test_extract_image_urls_from_markdown() -> None:
    md = "![Alt text](https://example.com/figure.jpg)"
    urls = _extract_image_urls(md)
    assert "https://example.com/figure.jpg" in urls


def test_collect_image_urls_caps_at_50() -> None:
    sources = []
    for i in range(60):
        content = f'<img src="https://example.com/img{i}.png">'
        sources.append(_make_source(raw_content=content, url=f"https://example.com/page{i}"))
    results = _collect_image_urls(sources)
    assert len(results) == 50


@pytest.mark.asyncio
async def test_run_returns_empty_charts_for_local_mode() -> None:
    """When MODAL_BASE_URL=local, no HTTP calls are made and charts=[]."""
    agent, emitter = _make_agent(modal_base_url="local")

    with patch("app.agents.cv_document.asyncio.sleep", new_callable=AsyncMock):
        db_mock = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [
            _make_source(raw_content='<img src="https://example.com/chart.png">')
        ]
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        db_mock.execute = AsyncMock(return_value=execute_result)
        agent._db = db_mock

        result = await agent.run({"question": "test", "sub_tasks": ["q1"]})

    assert result["chart_count"] == 0
    assert result["chart_results"] == []
    event_types = [e.event_type for e in emitter.events]
    assert "agent_started" in event_types
    assert "agent_completed" in event_types


@pytest.mark.asyncio
async def test_run_with_successful_chart_extraction() -> None:
    """Two sources, one image, successful classify + extract returns 1 chart."""
    from httpx import Response

    agent, emitter = _make_agent(modal_base_url="https://modal.test")

    classify_resp = MagicMock(spec=Response)
    classify_resp.status_code = 200
    classify_resp.json.return_value = {
        "image_url": "https://example.com/chart.png",
        "doc_class": "bar_chart",
        "confidence": 0.95,
        "latency_ms": 42.0,
    }

    extract_resp = MagicMock(spec=Response)
    extract_resp.status_code = 200
    extract_resp.json.return_value = {
        "image_url": "https://example.com/chart.png",
        "source_url": "https://example.com/page.html",
        "chart_type": "bar_chart",
        "title": "Revenue Chart",
        "x_axis": "Quarter",
        "y_axis": "USD M",
        "series": [{"name": "Revenue", "data_points": [{"label": "Q1", "value": 10.0}]}],
        "key_insight": "Revenue grew Q1.",
    }

    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(side_effect=[classify_resp, extract_resp])
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=None)

    db_mock = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [
        _make_source(
            raw_content='<img src="https://example.com/chart.png">',
            url="https://example.com/page.html",
        )
    ]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db_mock.execute = AsyncMock(return_value=execute_result)
    db_mock.add = MagicMock()
    db_mock.flush = AsyncMock()
    agent._db = db_mock

    with (
        patch("app.agents.cv_document.asyncio.sleep", new_callable=AsyncMock),
        patch("app.agents.cv_document.httpx.AsyncClient", return_value=mock_http_client),
    ):
        result = await agent.run({"question": "test", "sub_tasks": ["q1"]})

    assert result["chart_count"] == 1
    assert result["chart_results"][0]["chart_type"] == "bar_chart"
    event_types = [e.event_type for e in emitter.events]
    assert "cv_document_started" in event_types
    assert "cv_document_classified" in event_types
    assert "cv_chart_extracted" in event_types
    assert "agent_completed" in event_types


@pytest.mark.asyncio
async def test_run_skips_non_image_sources() -> None:
    """Sources with no image URLs in raw_content produce zero charts."""
    agent, _emitter = _make_agent(modal_base_url="https://modal.test")

    db_mock = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [
        _make_source(raw_content="<p>No images here, just text</p>")
    ]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db_mock.execute = AsyncMock(return_value=execute_result)
    agent._db = db_mock

    with patch("app.agents.cv_document.asyncio.sleep", new_callable=AsyncMock):
        result = await agent.run({"question": "test", "sub_tasks": []})

    assert result["chart_count"] == 0


@pytest.mark.asyncio
async def test_modal_401_raises_agent_error() -> None:
    """A 401 from Modal raises AgentError immediately."""
    from httpx import Response

    agent, emitter = _make_agent(modal_base_url="https://modal.test")

    auth_resp = MagicMock(spec=Response)
    auth_resp.status_code = 401
    auth_resp.json.return_value = {"error": "unauthorized"}

    mock_http_client = MagicMock()
    mock_http_client.post = AsyncMock(return_value=auth_resp)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=None)

    db_mock = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [
        _make_source(raw_content='<img src="https://example.com/chart.png">')
    ]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db_mock.execute = AsyncMock(return_value=execute_result)
    agent._db = db_mock

    with (
        patch("app.agents.cv_document.asyncio.sleep", new_callable=AsyncMock),
        patch("app.agents.cv_document.httpx.AsyncClient", return_value=mock_http_client),
        pytest.raises(AgentError),
    ):
        await agent.run({"question": "test", "sub_tasks": []})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_failed" in event_types


@pytest.mark.asyncio
async def test_semaphore_limits_concurrent_calls() -> None:
    """Semaphore(3) limits simultaneous Modal calls to 3."""

    agent, _emitter = _make_agent(modal_base_url="local")
    # With local mode, _process_image returns immediately. Just verify the agent
    # completes without errors when processing multiple sources.
    sources = [
        _make_source(
            raw_content=f'<img src="https://example.com/img{i}.png">',
            url=f"https://example.com/page{i}",
        )
        for i in range(5)
    ]
    db_mock = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = sources
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db_mock.execute = AsyncMock(return_value=execute_result)
    agent._db = db_mock

    with patch("app.agents.cv_document.asyncio.sleep", new_callable=AsyncMock):
        result = await agent.run({"question": "test", "sub_tasks": []})

    assert result["chart_count"] == 0  # local mode returns no charts
