"""Tests for WriterAgent chart data injection and chart_formatter (t-026)."""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.chart_formatter import format_charts_section


def _make_chart_dict(
    chart_type: str = "bar_chart",
    title: str = "Revenue by Region",
    source_url: str = "https://example.com/report.html",
) -> dict[str, Any]:
    return {
        "image_url": "https://example.com/chart.png",
        "source_url": source_url,
        "chart_type": chart_type,
        "title": title,
        "x_axis": "Region",
        "y_axis": "USD M",
        "series": [
            {
                "name": "2024",
                "data_points": [
                    {"label": "APAC", "value": 42.5},
                    {"label": "EMEA", "value": 31.2},
                ],
            }
        ],
        "key_insight": "APAC leads with $42.5M.",
    }


# ─────────────────────────────────────────────
# chart_formatter tests
# ─────────────────────────────────────────────


def test_format_charts_section_with_empty_list_returns_empty_string() -> None:
    result = format_charts_section([])
    assert result == ""


def test_format_charts_section_with_one_chart_returns_markdown() -> None:
    charts = [_make_chart_dict()]
    result = format_charts_section(charts)
    assert "## Data from Charts" in result
    assert "Revenue by Region" in result
    assert "https://example.com/report.html" in result
    assert "APAC: 42.5" in result
    assert "key insight" in result.lower() or "Key insight" in result


def test_format_charts_section_with_two_charts() -> None:
    charts = [
        _make_chart_dict(title="Chart One"),
        _make_chart_dict(title="Chart Two", chart_type="line_chart"),
    ]
    result = format_charts_section(charts)
    assert "Chart 1: Chart One" in result
    assert "Chart 2: Chart Two" in result
    assert "line_chart" in result


def test_format_charts_section_handles_null_title() -> None:
    chart = _make_chart_dict()
    chart["title"] = None
    result = format_charts_section([chart])
    assert "Untitled" in result


# ─────────────────────────────────────────────
# WriterAgent chart injection tests
# ─────────────────────────────────────────────


def _make_writer_agent() -> Any:
    from app.agents.base import EventEmitter
    from app.agents.writer import WriterAgent

    class FakeEmitter(EventEmitter):
        async def emit(self, event: Any) -> None:
            pass

    db = AsyncMock()
    session_id = uuid.uuid4()
    agent = WriterAgent(session_id=session_id, emitter=FakeEmitter(), db=db)
    return agent, db


@pytest.mark.asyncio
async def test_writer_prompt_includes_chart_data_when_charts_present() -> None:
    agent, db = _make_writer_agent()

    from app.models.source import Source
    mock_source = MagicMock(spec=Source)
    mock_source.url = "https://example.com"
    mock_source.title = "Test Source"
    mock_source.raw_content = "some content"
    mock_source.cleaned_content = "some content"
    mock_source.relevance_score = 0.9
    mock_source.sub_task_index = 0

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_source]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()

    captured_kwargs: dict[str, Any] = {}

    async def fake_create(**kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        content_block = MagicMock()
        content_block.type = "text"
        content_block.text = (
            "## Executive Summary\nTest report with chart data. "
            "[Source](https://example.com) [Source2](https://example.com) "
            "[Source3](https://example.com)"
        )
        msg = MagicMock()
        msg.content = [content_block]
        return msg

    agent._client = MagicMock()
    agent._client.messages = MagicMock()
    agent._client.messages.create = fake_create

    charts = [_make_chart_dict()]
    await agent.run({"question": "test question", "chart_results": charts, "sub_tasks": []})

    user_content = captured_kwargs["messages"][0]["content"]
    user_texts = [block["text"] for block in user_content if isinstance(block, dict)]
    combined = "\n".join(user_texts)
    assert "## Data from Charts" in combined
    assert "APAC: 42.5" in combined


@pytest.mark.asyncio
async def test_writer_prompt_has_no_chart_section_when_charts_absent() -> None:
    agent, db = _make_writer_agent()

    from app.models.source import Source
    mock_source = MagicMock(spec=Source)
    mock_source.url = "https://example.com"
    mock_source.title = "Test Source"
    mock_source.raw_content = "some content"
    mock_source.cleaned_content = "some content"
    mock_source.relevance_score = 0.9
    mock_source.sub_task_index = 0

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_source]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()

    captured_kwargs: dict[str, Any] = {}

    async def fake_create(**kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        content_block = MagicMock()
        content_block.type = "text"
        content_block.text = (
            "## Executive Summary\n\nThis is a test report without chart data. "
            "[Source A](https://a.com) [Source B](https://b.com) [Source C](https://c.com)\n\n"
            "## Conclusion\n\nNo charts were included in this analysis."
        )
        msg = MagicMock()
        msg.content = [content_block]
        return msg

    agent._client = MagicMock()
    agent._client.messages = MagicMock()
    agent._client.messages.create = fake_create

    # No chart_results key
    await agent.run({"question": "test question", "sub_tasks": []})

    user_content = captured_kwargs["messages"][0]["content"]
    user_texts = [block["text"] for block in user_content if isinstance(block, dict)]
    combined = "\n".join(user_texts)
    assert "## Data from Charts" not in combined
