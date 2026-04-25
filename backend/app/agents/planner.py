import asyncio
import json
import uuid
from typing import Any

import anthropic
import structlog

from app.agents.base import AgentEvent, AgentFatalError, EventEmitter, ResearchAgent

logger = structlog.get_logger(__name__)

PLANNER_MODEL = "claude-3-5-haiku-20241022"
MAX_RETRIES = 2

SYSTEM_PROMPT = """You are a research planning assistant. Given a business research question, \
decompose it into 3 to 10 independent sub-tasks. Each sub-task should be a specific search query \
or research angle that together will provide comprehensive coverage of the original question.

Respond with a JSON object in this exact format:
{
  "sub_tasks": [
    "specific search query or research angle 1",
    "specific search query or research angle 2",
    ...
  ]
}

Rules:
- Between 3 and 10 sub-tasks (inclusive)
- Each sub-task must be 10 to 200 characters
- Each sub-task must be a specific, actionable search query
- No sub-task may be empty or a duplicate
- Respond ONLY with the JSON object, no other text"""


class PlannerAgent(ResearchAgent):
    def __init__(self, session_id: uuid.UUID, emitter: EventEmitter) -> None:
        super().__init__(session_id, emitter)
        self._client = anthropic.AsyncAnthropic()

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        question: str = input_data["question"]

        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="planner",
            event_type="agent_started",
            payload={"agent": "planner"},
        ))

        sub_tasks = await self._decompose_with_retry(question)

        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="planner",
            event_type="agent_completed",
            payload={"agent": "planner", "sub_task_count": len(sub_tasks)},
        ))

        logger.info("planner.completed", session_id=str(self.session_id), count=len(sub_tasks))
        return {"sub_tasks": sub_tasks}

    async def _decompose_with_retry(self, question: str) -> list[str]:
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                sub_tasks = await self._call_llm(question)
                self._validate(sub_tasks)
                return sub_tasks
            except AgentFatalError:
                raise
            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    continue

        await self.emitter.emit(AgentEvent(
            session_id=self.session_id,
            agent_type="planner",
            event_type="agent_failed",
            payload={"agent": "planner", "error": str(last_error)},
        ))
        raise AgentFatalError(f"Planner failed after {MAX_RETRIES + 1} attempts: {last_error}")

    async def _call_llm(self, question: str) -> list[str]:
        response = await self._client.messages.create(
            model=PLANNER_MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": question}],
        )
        raw = response.content[0]
        if raw.type != "text":
            raise ValueError(f"Unexpected content type: {raw.type}")

        parsed = json.loads(raw.text)
        return list(parsed["sub_tasks"])

    def _validate(self, sub_tasks: list[str]) -> None:
        if len(sub_tasks) < 3:
            raise AgentFatalError(
                f"Planner returned {len(sub_tasks)} sub-tasks; minimum is 3"
            )
        if len(sub_tasks) > 10:
            raise AgentFatalError(
                f"Planner returned {len(sub_tasks)} sub-tasks; maximum is 10"
            )
        for task in sub_tasks:
            if not task or len(task.strip()) < 10:
                raise AgentFatalError(f"Sub-task too short: {task!r}")
