import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.main import app
from app.models.research_session import ResearchSession

_FAKE_SESSION_ID = uuid.uuid4()


def make_mock_db() -> AsyncSession:
    db = AsyncMock(spec=AsyncSession)

    async def fake_refresh(obj: ResearchSession) -> None:
        obj.id = _FAKE_SESSION_ID
        obj.status = "queued"

    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=fake_refresh)
    return db


@pytest.fixture(autouse=True)
def override_db_dependency() -> AsyncGenerator[None, None]:
    mock_db = make_mock_db()

    async def fake_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.lpush = AsyncMock(return_value=1)
    return redis


@pytest.mark.asyncio
async def test_create_research_returns_202_with_session_id(
    client: AsyncClient, mock_redis: AsyncMock
) -> None:
    with patch("app.services.research_service.get_redis", return_value=mock_redis):
        response = await client.post(
            "/api/research/create",
            json={"question": "What are the competitive dynamics in B2B SaaS CRM?"},
        )

    assert response.status_code == 202
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "queued"
    assert "/stream" in data["stream_url"]


@pytest.mark.asyncio
async def test_create_research_enqueues_to_redis(
    client: AsyncClient, mock_redis: AsyncMock
) -> None:
    with patch("app.services.research_service.get_redis", return_value=mock_redis):
        await client.post(
            "/api/research/create",
            json={"question": "Analyze electric vehicle battery supply chain risks"},
        )

    mock_redis.lpush.assert_awaited_once()
    queue_key = mock_redis.lpush.call_args[0][0]
    assert queue_key == "meridian:queue:sessions"


@pytest.mark.asyncio
async def test_create_research_question_too_short_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/research/create",
        json={"question": "Too short"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_research_question_too_long_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/research/create",
        json={"question": "x" * 2001},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_research_missing_question_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/research/create", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_research_stream_url_contains_session_id(
    client: AsyncClient, mock_redis: AsyncMock
) -> None:
    with patch("app.services.research_service.get_redis", return_value=mock_redis):
        response = await client.post(
            "/api/research/create",
            json={"question": "What drives enterprise software adoption decisions?"},
        )

    data = response.json()
    assert data["session_id"] in data["stream_url"]
