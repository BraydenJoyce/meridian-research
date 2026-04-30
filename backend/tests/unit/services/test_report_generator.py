"""Tests for report_generator PDF export service (t-034)."""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.report_generator import generate_pdf


def test_generate_pdf_returns_bytes() -> None:
    pdf = generate_pdf("## Hello\n\nThis is a test report.")
    assert isinstance(pdf, bytes)
    assert len(pdf) > 0


def test_pdf_starts_with_pdf_magic_bytes() -> None:
    pdf = generate_pdf("## Report\n\nContent here.")
    assert pdf[:4] == b"%PDF"


def test_generate_pdf_with_markdown_links() -> None:
    md = "## Summary\n\nSee [Source](https://example.com) for details."
    pdf = generate_pdf(md)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_export_endpoint_returns_404_for_missing_session() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.core.dependencies import get_db
    from app.main import app

    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    db_mock = AsyncMock()
    db_mock.execute = AsyncMock(return_value=execute_result)

    async def override_get_db() -> Any:
        yield db_mock

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/research/{uuid.uuid4()}/export")

    app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_endpoint_returns_pdf_content_type() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.core.dependencies import get_db
    from app.main import app

    session_id = uuid.uuid4()

    session_mock = MagicMock()
    session_mock.id = session_id
    session_mock.report_markdown = "## Report\n\nContent here. [Source](https://example.com)"

    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=session_mock)
    db_mock = AsyncMock()
    db_mock.execute = AsyncMock(return_value=execute_result)

    async def override_get_db() -> Any:
        yield db_mock

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/research/{session_id}/export")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
