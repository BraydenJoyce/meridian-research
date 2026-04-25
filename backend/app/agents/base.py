import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    """A single event emitted by an agent. Written to agent_events table and published to SSE."""

    session_id: uuid.UUID
    agent_type: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventEmitter:
    """Injected into each agent. Handles persistence and SSE publication."""

    async def emit(self, event: AgentEvent) -> None:
        """
        1. Atomically fetch-and-increment sequence number from Redis.
        2. INSERT into agent_events with that sequence_number.
        3. PUBLISH SSE-formatted event to Redis pub/sub channel meridian:session:{session_id}.

        Raises RuntimeError if Redis or DB write fails.
        """
        raise NotImplementedError


class ResearchAgent(ABC):
    """
    Base class for all research agents. Instantiated per-session.
    Do not share mutable state between sessions.
    """

    def __init__(self, session_id: uuid.UUID, emitter: EventEmitter) -> None:
        self.session_id = session_id
        self.emitter = emitter

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the agent's work.

        Args:
            input_data: Pipeline context dict, merged with prior agent outputs.

        Returns:
            Agent output dict. Merged into pipeline context for next agent.

        Raises:
            AgentError: Recoverable failure — pipeline may continue.
            AgentFatalError: Unrecoverable failure — pipeline must abort.
        """
        ...


class AgentError(Exception):
    """Recoverable agent failure. Pipeline may continue."""


class AgentFatalError(Exception):
    """Unrecoverable agent failure. Pipeline must abort and mark session failed."""
