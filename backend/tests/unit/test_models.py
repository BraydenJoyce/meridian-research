import uuid

import pytest
from pydantic import ValidationError

from app.models.agent_event import AgentEvent
from app.models.research_session import ResearchSession
from app.models.source import Source
from app.schemas.research_session import ResearchSessionCreate


def test_research_session_model_defaults() -> None:
    session = ResearchSession(question="What are the latest AI trends in healthcare?")
    assert session.status == "queued"
    assert isinstance(session.id, uuid.UUID)


def test_source_model_instantiation() -> None:
    session_id = uuid.uuid4()
    source = Source(
        session_id=session_id,
        url="https://example.com/article",
        sub_task_index=0,
    )
    assert isinstance(source.id, uuid.UUID)
    assert source.session_id == session_id
    assert source.url == "https://example.com/article"
    assert source.sub_task_index == 0


def test_agent_event_model_instantiation() -> None:
    session_id = uuid.uuid4()
    event = AgentEvent(
        session_id=session_id,
        agent_type="planner",
        event_type="agent_started",
        payload={"message": "Planner starting"},
        sequence_number=1,
    )
    assert isinstance(event.id, uuid.UUID)
    assert event.session_id == session_id
    assert event.agent_type == "planner"
    assert event.event_type == "agent_started"
    assert event.sequence_number == 1


def test_research_session_schema_validation() -> None:
    with pytest.raises(ValidationError):
        ResearchSessionCreate(question="short")


def test_research_session_schema_valid() -> None:
    schema = ResearchSessionCreate(
        question="What are the key trends in renewable energy in 2026?"
    )
    assert len(schema.question) >= 10
