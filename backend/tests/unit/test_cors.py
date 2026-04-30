"""Tests for CORS middleware configuration (t-050)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cors_allowed_origin_returns_header(client: AsyncClient) -> None:
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_disallowed_origin_omits_header(client: AsyncClient) -> None:
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "http://evil.example.com"


@pytest.mark.asyncio
async def test_cors_allows_credentials(client: AsyncClient) -> None:
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_get_request_includes_origin_header(client: AsyncClient) -> None:
    from unittest.mock import AsyncMock, patch

    with patch("app.api.health._check_db", new=AsyncMock(return_value="ok")), \
         patch("app.api.health._check_redis", new=AsyncMock(return_value="ok")):
        response = await client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
