import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.main import app
from app.models.agent_event import AgentEvent as AgentEventModel
from app.models.research_session import ResearchSession

SESSION_ID = uuid.uuid4()
MISSING_ID = uuid.uuid4()


def _make_event(
    seq: int,
    event_type: str = "agent_started",
    agent_type: str = "planner",
) -> AgentEventModel:
    evt = MagicMock(spec=AgentEventModel)
    evt.id = uuid.uuid4()
    evt.session_id = SESSION_ID
    evt.sequence_number = seq
    evt.event_type = event_type
    evt.agent_type = agent_type
    evt.payload = {"agent": agent_type}
    evt.created_at = datetime.now(UTC)
    return evt


def _make_session(status: str = "running") -> MagicMock:
    s = MagicMock(spec=ResearchSession)
    s.id = SESSION_ID
    s.status = status
    s.report_markdown = None
    return s


class _FakeExecuteResult:
    def __init__(self, rows: list[Any], scalar: Any = None) -> None:
        self._rows = rows
        self._scalar = scalar

    def scalars(self) -> "_FakeExecuteResult":
        return self

    def all(self) -> list[Any]:
        return self._rows

    def scalar_one_or_none(self) -> Any:
        return self._scalar


def make_mock_db_for_stream(
    session_exists: bool = True,
    events_sequence: list[list[AgentEventModel]] | None = None,
    session_statuses: list[str] | None = None,
) -> AsyncSession:
    db = AsyncMock(spec=AsyncSession)
    call_count = [0]
    events_sequence = events_sequence or [[]]
    session_statuses = session_statuses or ["completed"]

    session_obj = _make_session("running") if session_exists else None

    async def fake_execute(stmt: Any, *args: Any, **kwargs: Any) -> _FakeExecuteResult:
        n = call_count[0]
        call_count[0] += 1

        # First call is the 404 check in the route handler
        if n == 0:
            return _FakeExecuteResult([], scalar=session_obj)

        # Alternating: events query, then session status query
        pair_idx = (n - 1) // 2
        is_events_call = (n - 1) % 2 == 0

        if is_events_call:
            evts = events_sequence[min(pair_idx, len(events_sequence) - 1)]
            return _FakeExecuteResult(evts)
        else:
            status = session_statuses[min(pair_idx, len(session_statuses) - 1)]
            sess = _make_session(status) if session_exists else None
            return _FakeExecuteResult([], scalar=sess)

    db.execute = fake_execute  # type: ignore[method-assign]
    return db


@pytest.fixture(autouse=True)
def clear_overrides() -> AsyncGenerator[None, None]:
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_stream_returns_404_for_missing_session(client: AsyncClient) -> None:
    def make_missing_db() -> AsyncSession:
        db = AsyncMock(spec=AsyncSession)

        async def fake_execute(stmt: Any, *args: Any, **kwargs: Any) -> _FakeExecuteResult:
            return _FakeExecuteResult([], scalar=None)

        db.execute = fake_execute  # type: ignore[method-assign]
        return db

    async def fake_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield make_missing_db()

    app.dependency_overrides[get_db] = fake_get_db

    response = await client.get(f"/api/research/{MISSING_ID}/stream")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_returns_200_with_sse_content_type(client: AsyncClient) -> None:
    mock_db = make_mock_db_for_stream(
        events_sequence=[[]],
        session_statuses=["completed"],
    )

    async def fake_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db

    response = await client.get(f"/api/research/{SESSION_ID}/stream")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_stream_sends_events_in_sse_format(client: AsyncClient) -> None:
    events = [
        _make_event(1, "agent_started", "planner"),
        _make_event(2, "agent_completed", "planner"),
    ]
    mock_db = make_mock_db_for_stream(
        events_sequence=[events],
        session_statuses=["completed"],
    )

    async def fake_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db

    response = await client.get(f"/api/research/{SESSION_ID}/stream")
    body = response.text

    lines = [line for line in body.split("\n") if line.startswith("data:")]
    assert len(lines) >= 2

    first = json.loads(lines[0][len("data: "):])
    assert "event_type" in first
    assert first["event_type"] == "agent_started"


@pytest.mark.asyncio
async def test_stream_closes_on_completed_status(client: AsyncClient) -> None:
    mock_db = make_mock_db_for_stream(
        events_sequence=[[]],
        session_statuses=["completed"],
    )

    async def fake_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db

    response = await client.get(f"/api/research/{SESSION_ID}/stream")
    assert response.status_code == 200

    body = response.text
    done_lines = [
        line for line in body.split("\n")
        if line.startswith("data:") and "done" in line
    ]
    assert len(done_lines) >= 1
    done_payload = json.loads(done_lines[0][len("data: "):])
    assert done_payload["event_type"] == "done"
    assert done_payload["status"] == "completed"


@pytest.mark.asyncio
async def test_stream_closes_on_failed_status(client: AsyncClient) -> None:
    mock_db = make_mock_db_for_stream(
        events_sequence=[[]],
        session_statuses=["failed"],
    )

    async def fake_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db

    response = await client.get(f"/api/research/{SESSION_ID}/stream")
    body = response.text
    done_lines = [
        line for line in body.split("\n")
        if line.startswith("data:") and "done" in line
    ]
    assert len(done_lines) >= 1
    done_payload = json.loads(done_lines[0][len("data: "):])
    assert done_payload["status"] == "failed"
