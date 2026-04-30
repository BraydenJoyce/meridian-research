from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_ok(client: AsyncClient) -> None:
    with patch("app.api.health._check_db", new=AsyncMock(return_value="ok")), \
         patch("app.api.health._check_redis", new=AsyncMock(return_value="ok")):
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_check_content_type(client: AsyncClient) -> None:
    with patch("app.api.health._check_db", new=AsyncMock(return_value="ok")), \
         patch("app.api.health._check_redis", new=AsyncMock(return_value="ok")):
        response = await client.get("/health")
    assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_health_returns_version(client: AsyncClient) -> None:
    with patch("app.api.health._check_db", new=AsyncMock(return_value="ok")), \
         patch("app.api.health._check_redis", new=AsyncMock(return_value="ok")):
        response = await client.get("/health")
    data = response.json()
    assert "version" in data
    assert data["version"] == "1.0.0-beta"


@pytest.mark.asyncio
async def test_health_returns_db_status(client: AsyncClient) -> None:
    with patch("app.api.health._check_db", new=AsyncMock(return_value="ok")), \
         patch("app.api.health._check_redis", new=AsyncMock(return_value="ok")):
        response = await client.get("/health")
    data = response.json()
    assert "db" in data
    assert data["db"] in ("ok", "error")


@pytest.mark.asyncio
async def test_health_returns_redis_status(client: AsyncClient) -> None:
    with patch("app.api.health._check_db", new=AsyncMock(return_value="ok")), \
         patch("app.api.health._check_redis", new=AsyncMock(return_value="error")):
        response = await client.get("/health")
    data = response.json()
    assert "redis" in data
    assert data["redis"] == "error"
    assert data["status"] == "degraded"
