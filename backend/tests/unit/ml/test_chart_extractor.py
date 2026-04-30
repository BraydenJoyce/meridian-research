"""Tests for the Claude Vision chart data extractor."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from ml.inference.chart_extractor import ChartExtractor


def _make_png_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _valid_chart_json() -> str:
    return json.dumps(
        {
            "title": "Q1 Revenue by Region",
            "x_axis": "Region",
            "y_axis": "Revenue (USD M)",
            "series": [
                {
                    "name": "2024",
                    "data_points": [
                        {"label": "APAC", "value": 42.5},
                        {"label": "EMEA", "value": 31.2},
                    ],
                }
            ],
            "key_insight": "APAC leads revenue at $42.5M, outpacing EMEA by 36%.",
        }
    )


def _make_mock_client(response_text: str) -> MagicMock:
    """Build a mock anthropic.AsyncAnthropic client returning a fixed message."""
    content_block = MagicMock()
    content_block.text = response_text
    message = MagicMock()
    message.content = [content_block]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=message)
    return client


@pytest.mark.asyncio
async def test_extract_returns_chart_result_for_bar_chart() -> None:
    client = _make_mock_client(_valid_chart_json())
    extractor = ChartExtractor(client=client)

    result = await extractor.extract(
        image_bytes=_make_png_bytes(),
        doc_class="bar_chart",
        source_url="https://example.com/report.html",
        image_url="https://example.com/chart.png",
    )

    assert result is not None
    assert result.chart_type == "bar_chart"
    assert result.key_insight != ""
    assert len(result.series) >= 1


@pytest.mark.asyncio
async def test_extract_returns_none_for_non_chart() -> None:
    client = _make_mock_client('{"error": "not a chart"}')
    extractor = ChartExtractor(client=client)

    result = await extractor.extract(
        image_bytes=_make_png_bytes(),
        doc_class="bar_chart",
        source_url="https://example.com/page.html",
    )

    assert result is None


@pytest.mark.asyncio
async def test_extract_retries_on_bad_json() -> None:
    content1 = MagicMock()
    content1.text = "not valid json at all"
    content2 = MagicMock()
    content2.text = _valid_chart_json()

    msg1, msg2 = MagicMock(), MagicMock()
    msg1.content = [content1]
    msg2.content = [content2]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    extractor = ChartExtractor(client=client)

    result = await extractor.extract(
        image_bytes=_make_png_bytes(),
        doc_class="line_chart",
        source_url="https://example.com/report.html",
    )

    assert result is not None
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_extract_returns_none_after_two_failures() -> None:
    client = _make_mock_client("not json")
    extractor = ChartExtractor(client=client)

    result = await extractor.extract(
        image_bytes=_make_png_bytes(),
        doc_class="bar_chart",
        source_url="https://example.com/report.html",
    )

    assert result is None
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_cache_control_present() -> None:
    client = _make_mock_client(_valid_chart_json())
    extractor = ChartExtractor(client=client)

    await extractor.extract(
        image_bytes=_make_png_bytes(),
        doc_class="table",
        source_url="https://example.com/report.html",
    )

    call_kwargs: dict[str, Any] = client.messages.create.call_args.kwargs
    system_messages: list[dict[str, Any]] = call_kwargs.get("system", [])
    assert any(
        msg.get("cache_control") == {"type": "ephemeral"} for msg in system_messages
    ), "Expected cache_control: {type: ephemeral} on system message"


@pytest.mark.asyncio
async def test_extract_returns_none_on_api_exception() -> None:
    import anthropic as _anthropic

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        side_effect=_anthropic.APIStatusError(
            "rate limit",
            response=MagicMock(status_code=429, headers={}),
            body={},
        )
    )
    extractor = ChartExtractor(client=client)

    result = await extractor.extract(
        image_bytes=_make_png_bytes(),
        doc_class="pie_chart",
        source_url="https://example.com/report.html",
    )

    assert result is None
