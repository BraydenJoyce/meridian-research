import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentEvent, AgentFatalError, EventEmitter
from app.agents.planner import PlannerAgent

SESSION_ID = uuid.uuid4()
VALID_QUESTION = "What are the competitive dynamics in B2B SaaS CRM market in 2026?"

VALID_SUB_TASKS = [
    "Salesforce market share and competitive positioning 2026",
    "HubSpot vs Salesforce feature comparison enterprise",
    "Emerging CRM startups Series B funding activity 2025 2026",
    "AI-powered CRM features adoption rates enterprise market",
]


class FakeEmitter(EventEmitter):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[AgentEvent] = []

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


def make_mock_response(sub_tasks: list[str]) -> MagicMock:
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = json.dumps({"sub_tasks": sub_tasks})
    response = MagicMock()
    response.content = [content_block]
    return response


@pytest.fixture
def emitter() -> FakeEmitter:
    return FakeEmitter()


@pytest.fixture
def agent(emitter: FakeEmitter) -> PlannerAgent:
    return PlannerAgent(session_id=SESSION_ID, emitter=emitter)


@pytest.mark.asyncio
async def test_planner_returns_sub_tasks_for_valid_question(
    agent: PlannerAgent, emitter: FakeEmitter
) -> None:
    mock_response = make_mock_response(VALID_SUB_TASKS)

    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        result = await agent.run({"question": VALID_QUESTION, "session_id": SESSION_ID})

    assert "sub_tasks" in result
    assert len(result["sub_tasks"]) == len(VALID_SUB_TASKS)
    assert result["sub_tasks"] == VALID_SUB_TASKS


@pytest.mark.asyncio
async def test_planner_emits_agent_started_and_completed(
    agent: PlannerAgent, emitter: FakeEmitter
) -> None:
    mock_response = make_mock_response(VALID_SUB_TASKS)

    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        await agent.run({"question": VALID_QUESTION, "session_id": SESSION_ID})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_started" in event_types
    assert "agent_completed" in event_types


@pytest.mark.asyncio
async def test_planner_uses_cache_control_on_system_prompt(
    agent: PlannerAgent,
) -> None:
    mock_response = make_mock_response(VALID_SUB_TASKS)

    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        await agent.run({"question": VALID_QUESTION, "session_id": SESSION_ID})

    call_kwargs = mock_create.call_args[1]
    system_blocks = call_kwargs["system"]
    assert isinstance(system_blocks, list)
    assert any(
        block.get("cache_control", {}).get("type") == "ephemeral"
        for block in system_blocks
    )


@pytest.mark.asyncio
async def test_planner_retries_on_api_timeout(
    agent: PlannerAgent, emitter: FakeEmitter
) -> None:
    import anthropic as anthropic_module

    mock_response = make_mock_response(VALID_SUB_TASKS)

    with patch.object(
        agent._client.messages,
        "create",
        new_callable=AsyncMock,
        side_effect=[
            anthropic_module.APITimeoutError(request=MagicMock()),
            mock_response,
        ],
    ) as mock_create:
        with patch("app.agents.planner.asyncio.sleep", new_callable=AsyncMock):
            result = await agent.run({"question": VALID_QUESTION, "session_id": SESSION_ID})

    assert mock_create.await_count == 2
    assert len(result["sub_tasks"]) > 0


@pytest.mark.asyncio
async def test_planner_raises_fatal_error_when_too_few_subtasks(
    agent: PlannerAgent,
) -> None:
    mock_response = make_mock_response(["only one sub-task here, too short"])

    with patch.object(agent._client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response
        with pytest.raises(AgentFatalError, match="minimum is 3"):
            await agent.run({"question": VALID_QUESTION, "session_id": SESSION_ID})


@pytest.mark.asyncio
async def test_planner_raises_fatal_error_after_exhausted_retries(
    agent: PlannerAgent,
) -> None:
    import anthropic as anthropic_module

    with patch.object(
        agent._client.messages,
        "create",
        new_callable=AsyncMock,
        side_effect=anthropic_module.APITimeoutError(request=MagicMock()),
    ):
        with patch("app.agents.planner.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(AgentFatalError, match="attempts"):
                await agent.run({"question": VALID_QUESTION, "session_id": SESSION_ID})


@pytest.mark.asyncio
async def test_planner_emits_agent_failed_on_fatal_error(
    agent: PlannerAgent, emitter: FakeEmitter
) -> None:
    import anthropic as anthropic_module

    with patch.object(
        agent._client.messages,
        "create",
        new_callable=AsyncMock,
        side_effect=anthropic_module.APITimeoutError(request=MagicMock()),
    ):
        with patch("app.agents.planner.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(AgentFatalError):
                await agent.run({"question": VALID_QUESTION, "session_id": SESSION_ID})

    event_types = [e.event_type for e in emitter.events]
    assert "agent_failed" in event_types
