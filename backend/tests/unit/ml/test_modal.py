"""Tests for the Modal CV inference server FastAPI app (ml/inference/api.py)."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient, Response
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "backend"))

from ml.inference.api import create_app

from app.schemas.cv import ChartResult, DataPoint, SeriesItem


def _make_png_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), color=(80, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _valid_chart_result() -> ChartResult:
    return ChartResult(
        image_url="https://example.com/chart.png",
        source_url="https://example.com/report.html",
        chart_type="bar_chart",
        title="Test Chart",
        x_axis="Category",
        y_axis="Value",
        series=[
            SeriesItem(
                name="Series A",
                data_points=[DataPoint(label="X", value=1.0)],
            )
        ],
        key_insight="A is highest.",
    )


def _make_mock_classifier() -> MagicMock:
    from ml.inference.classifier import CLASS_NAMES, ClassificationResult

    result = ClassificationResult(
        predicted_class=0,
        class_name="bar_chart",
        confidence=0.95,
        all_scores={
            name: (0.95 if i == 0 else 0.007) for i, name in enumerate(CLASS_NAMES)
        },
    )
    clf = MagicMock()
    clf.classify.return_value = result
    return clf


def _make_mock_extractor(return_value: ChartResult | None = None) -> MagicMock:
    extractor = MagicMock()
    extractor.extract = AsyncMock(return_value=return_value)
    return extractor


def _make_httpx_mock(content: bytes, status_code: int = 200) -> MagicMock:
    """Build a mock for httpx.AsyncClient that returns fixed content."""
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = status_code
    mock_response.content = content
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model" in data


@pytest.mark.asyncio
async def test_classify_endpoint_returns_classification() -> None:
    clf = _make_mock_classifier()
    app = create_app(classifier=clf)
    mock_client = _make_httpx_mock(content=_make_png_bytes())

    with patch("ml.inference.api.httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/classify",
                json={
                    "image_url": "https://example.com/chart.png",
                    "session_id": "test-session",
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_class"] == "bar_chart"
    assert 0.0 <= data["confidence"] <= 1.0
    assert "latency_ms" in data


@pytest.mark.asyncio
async def test_extract_chart_endpoint_with_mocked_extractor() -> None:
    extractor = _make_mock_extractor(return_value=_valid_chart_result())
    app = create_app(chart_extractor=extractor)
    mock_client = _make_httpx_mock(content=_make_png_bytes())

    with patch("ml.inference.api.httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/extract-chart",
                json={
                    "image_url": "https://example.com/chart.png",
                    "session_id": "test-session",
                    "source_url": "https://example.com/report.html",
                    "doc_class": "bar_chart",
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data is not None
    assert data["chart_type"] == "bar_chart"


@pytest.mark.asyncio
async def test_extract_chart_null_response_passthrough() -> None:
    extractor = _make_mock_extractor(return_value=None)
    app = create_app(chart_extractor=extractor)
    mock_client = _make_httpx_mock(content=_make_png_bytes())

    with patch("ml.inference.api.httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/extract-chart",
                json={
                    "image_url": "https://example.com/chart.png",
                    "session_id": "test-session",
                    "source_url": "https://example.com/report.html",
                    "doc_class": "bar_chart",
                },
            )

    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.asyncio
async def test_extract_chart_unsupported_doc_class_returns_422() -> None:
    extractor = _make_mock_extractor()
    app = create_app(chart_extractor=extractor)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/extract-chart",
            json={
                "image_url": "https://example.com/chart.png",
                "session_id": "test-session",
                "source_url": "https://example.com/report.html",
                "doc_class": "diagram",
            },
        )
    assert resp.status_code == 422
