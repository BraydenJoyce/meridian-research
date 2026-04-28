import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentEvent, EventEmitter
from app.agents.planner import SYSTEM_PROMPT, PlannerAgent
from app.services.rag_service import RagContext

SESSION_ID = uuid.uuid4()

VALID_SUB_TASKS = [
    "CRM market share analysis 2025 global statistics",
    "Salesforce HubSpot competitive landscape enterprise",
    "AI-powered CRM adoption trends small business",
]

VALID_LLM_RESPONSE = json.dumps({"sub_tasks": VALID_SUB_TASKS})


class FakeEmitter(EventEmitter):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[AgentEvent] = []

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


def make_mock_message(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def make_rag_context(idx: int) -> RagContext:
    return RagContext(
        source_id=f"src-{idx}",
        url=f"https://example{idx}.com/article",
        content_snippet=f"Prior research finding number {idx} about the CRM market.",
        quality_score=0.85,
        relevance_score=0.9 - idx * 0.05,
    )


@pytest.fixture
def emitter() -> FakeEmitter:
    return FakeEmitter()


@pytest.fixture
def agent_no_rag(emitter: FakeEmitter) -> PlannerAgent:
    return PlannerAgent(session_id=SESSION_ID, emitter=emitter)


@pytest.fixture
def mock_qdrant() -> MagicMock:
    return MagicMock()


@pytest.fixture
def agent_with_rag(emitter: FakeEmitter, mock_qdrant: MagicMock) -> PlannerAgent:
    return PlannerAgent(session_id=SESSION_ID, emitter=emitter, qdrant_client=mock_qdrant)


# ---------------------------------------------------------------------------
# Test 1: context_injected_when_rag_returns_results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_injected_when_rag_returns_results(
    agent_with_rag: PlannerAgent,
) -> None:
    """When get_context returns results the system prompt passed to the LLM
    must contain the 'Relevant prior research context' section."""
    rag_results = [make_rag_context(0), make_rag_context(1)]

    captured_system: list[Any] = []

    async def fake_create(**kwargs: Any) -> Any:
        captured_system.extend(kwargs.get("system", []))
        return make_mock_message(VALID_LLM_RESPONSE)

    with patch(
        "app.services.rag_service.get_context", return_value=rag_results
    ), patch.object(
        agent_with_rag._client.messages,
        "create",
        new_callable=AsyncMock,
        side_effect=fake_create,
    ):
        result = await agent_with_rag.run({"question": "What is the CRM market like?"})

    assert "sub_tasks" in result
    assert len(result["sub_tasks"]) == 3

    # The system block text must contain the RAG injection header
    system_texts = [block["text"] for block in captured_system if "text" in block]
    combined = "\n".join(system_texts)
    assert "Relevant prior research context" in combined


# ---------------------------------------------------------------------------
# Test 2: planner_works_without_rag_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planner_works_without_rag_context(agent_no_rag: PlannerAgent) -> None:
    """With qdrant_client=None the planner must complete successfully without
    calling get_context at all and return the expected sub_tasks."""
    with patch(
        "app.services.rag_service.get_context"
    ) as mock_get_context, patch.object(
        agent_no_rag._client.messages,
        "create",
        new_callable=AsyncMock,
        return_value=make_mock_message(VALID_LLM_RESPONSE),
    ):
        result = await agent_no_rag.run({"question": "What is the CRM market like?"})

    mock_get_context.assert_not_called()
    assert result["sub_tasks"] == VALID_SUB_TASKS


# ---------------------------------------------------------------------------
# Test 3: planner_degrades_gracefully_when_rag_empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planner_degrades_gracefully_when_rag_empty(
    agent_with_rag: PlannerAgent,
) -> None:
    """When get_context returns [] the planner must still succeed using the
    base SYSTEM_PROMPT (no injection appended)."""
    captured_system: list[Any] = []

    async def fake_create(**kwargs: Any) -> Any:
        captured_system.extend(kwargs.get("system", []))
        return make_mock_message(VALID_LLM_RESPONSE)

    with patch(
        "app.services.rag_service.get_context", return_value=[]
    ), patch.object(
        agent_with_rag._client.messages,
        "create",
        new_callable=AsyncMock,
        side_effect=fake_create,
    ):
        result = await agent_with_rag.run({"question": "What is the CRM market like?"})

    assert result["sub_tasks"] == VALID_SUB_TASKS

    # The system prompt must be exactly SYSTEM_PROMPT — no extra context appended
    system_texts = [block["text"] for block in captured_system if "text" in block]
    combined = "\n".join(system_texts)
    assert "Relevant prior research context" not in combined
    assert SYSTEM_PROMPT in combined
