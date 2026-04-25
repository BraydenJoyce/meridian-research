# ADR-003: Agent Interface Contracts

## Status
Accepted

## Context
The Milestone 1 research pipeline runs four agents in sequence: Planner, WebSearch, ETL, Writer. Each agent is an isolated async Python class. The pipeline runner in `backend/app/pipeline/runner.py` drives the sequence, passes outputs between agents, and handles failures.

Without a strict interface contract, agents will make incompatible assumptions about their inputs and outputs, causing integration failures that are hard to debug. This ADR defines the exact Python abstract base class, the input/output data models, and the `agent_events.payload` schema for every event type each agent emits.

All agents must implement the `ResearchAgent` ABC. No agent may communicate directly with another agent — all inter-agent data passes through the pipeline runner as return values. All agents must emit events via the provided `EventEmitter` — no agent writes directly to the SSE connection or to Redis.

## Decision

### Abstract base class

**File:** `backend/app/agents/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import uuid
from datetime import datetime, timezone


@dataclass
class AgentEvent:
    """A single event emitted by an agent. Written to agent_events table and published to SSE."""
    session_id: uuid.UUID
    agent_type: str        # matches agent_events.agent_type CHECK constraint
    event_type: str        # matches agent_events.event_type CHECK constraint
    payload: dict[str, Any]


class EventEmitter:
    """Injected into each agent. Handles persistence and SSE publication."""

    async def emit(self, event: AgentEvent) -> None:
        """
        1. Atomically fetch-and-increment sequence number from Redis.
        2. INSERT into agent_events with that sequence_number.
        3. PUBLISH SSE-formatted event to Redis pub/sub channel meridian:session:{session_id}.
        Raises RuntimeError if Redis or DB write fails — agent must propagate the exception.
        """
        raise NotImplementedError  # implemented in backend/app/services/emitter.py


class ResearchAgent(ABC):
    """
    Every research agent implements this interface.
    Agents are instantiated per-session. Do not share mutable state between sessions.
    """

    def __init__(self, session_id: uuid.UUID, emitter: EventEmitter) -> None:
        self.session_id = session_id
        self.emitter = emitter

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the agent's work.

        Parameters
        ----------
        input_data : dict
            The output dict returned by the previous agent in the pipeline,
            merged with the base session context (see Pipeline Context below).
            On the first agent (Planner), input_data contains only the base session context.

        Returns
        -------
        dict
            Agent output. Keys defined per-agent below. The pipeline runner
            merges this dict into the running context and passes it to the next agent.

        Raises
        ------
        AgentError
            Raised for recoverable failures (e.g. one search sub-task fails).
            The pipeline runner logs the error and continues if possible.
        AgentFatalError
            Raised for unrecoverable failures (e.g. Planner produces zero sub-tasks).
            The pipeline runner marks the session as failed immediately.
        """
        ...


class AgentError(Exception):
    """Recoverable agent failure. Pipeline may continue."""
    pass


class AgentFatalError(Exception):
    """Unrecoverable agent failure. Pipeline must abort and mark session failed."""
    pass
```

### Pipeline context (base session data passed to every agent)

The pipeline runner constructs this dict from the `research_sessions` row before calling the first agent. Every subsequent agent receives the accumulated merge of this context plus all prior agent outputs.

```python
{
    "session_id": uuid.UUID,        # research_sessions.id
    "question": str,                # the original research question
    "created_at": datetime,         # research_sessions.created_at (UTC)
}
```

---

### Agent 1 — Planner

**Class:** `backend/app/agents/planner.py::PlannerAgent`
**agent_type value:** `"planner"`

**Responsibility:** Decompose the research question into 3–10 independent sub-task strings. Each sub-task is a specific search query or research angle. The Planner calls an LLM (model: `claude-3-5-haiku-20241022` for cost efficiency) with a structured prompt and parses the response into a list.

**Input (from pipeline context):**
```python
{
    "session_id": uuid.UUID,
    "question": str,
    "created_at": datetime,
}
```

**Output (merged into pipeline context):**
```python
{
    "sub_tasks": list[str],   # 3–10 non-empty strings, each 10–200 chars
}
```

**Validation rules (raise `AgentFatalError` if violated):**
- `len(sub_tasks) < 3` — too few sub-tasks to produce a useful report
- `len(sub_tasks) > 10` — reject; retry with a stricter prompt (counted as one attempt)
- Any sub-task string is empty or shorter than 10 characters

**Events emitted (in order):**

| event_type | payload keys | description |
|---|---|---|
| `agent_started` | `{"agent": "planner"}` | Emitted before LLM call |
| `agent_completed` | `{"agent": "planner", "sub_task_count": int}` | Emitted after successful parse |
| `agent_failed` | `{"agent": "planner", "error": str}` | Emitted before raising AgentFatalError |

**PostgreSQL side effect:** After successful output, the pipeline runner (not the agent itself) updates `research_sessions.sub_tasks` with the serialized list.

---

### Agent 2 — WebSearch

**Class:** `backend/app/agents/web_search.py::WebSearchAgent`
**agent_type value:** `"web_search"`

**Responsibility:** For each sub-task string, execute a web search and fetch source content. The agent runs all sub-task searches concurrently using `asyncio.gather`. Each sub-task must retrieve at least 5 source URLs; the session as a whole must accumulate at least 20 sources. Sources are written to the `sources` table by the agent (not the pipeline runner).

**Search API:** Tavily Search API (`POST https://api.tavily.com/search`). API key from environment variable `TAVILY_API_KEY`. Request: `{"query": sub_task, "max_results": 10, "include_raw_content": true}`.

**Input (from pipeline context):**
```python
{
    "session_id": uuid.UUID,
    "question": str,
    "sub_tasks": list[str],
}
```

**Output (merged into pipeline context):**
```python
{
    "source_ids": list[uuid.UUID],  # UUIDs of all sources inserted into sources table
    "source_count": int,            # total sources retrieved (>= 20)
}
```

**Failure handling:**
- If a single sub-task search fails (network error, API timeout), emit `sub_task_completed` with `{"status": "failed", "error": str}` and continue with remaining sub-tasks. Raise `AgentError` after all sub-tasks complete if fewer than 20 total sources were retrieved.
- If fewer than 20 sources total: raise `AgentFatalError`.

**Events emitted (in order, across all sub-tasks):**

| event_type | payload keys | description |
|---|---|---|
| `agent_started` | `{"agent": "web_search", "sub_task_count": int}` | Before first search |
| `sub_task_started` | `{"sub_task_index": int, "query": str}` | Before each search call |
| `sub_task_completed` | `{"sub_task_index": int, "source_count": int, "status": "ok"\|"failed", "error": str\|null}` | After each search resolves |
| `source_fetched` | `{"source_id": str, "url": str, "title": str\|null}` | After each source row is inserted |
| `agent_completed` | `{"agent": "web_search", "total_sources": int}` | After all sub-tasks done |
| `agent_failed` | `{"agent": "web_search", "error": str}` | Before raising AgentFatalError |

---

### Agent 3 — ETL

**Class:** `backend/app/agents/etl.py::ETLAgent`
**agent_type value:** `"etl"`

**Responsibility:** Load all sources for the session from PostgreSQL into Polars DataFrames, run DuckDB SQL transforms (deduplicate by URL, score relevance against the original question, extract named entities), write processed results back to the `sources` table, and upsert source embeddings into Qdrant.

**DuckDB usage:** One in-process `:memory:` DuckDB connection per `run()` call. Load Polars DataFrames into DuckDB via `duckdb.register("sources_df", polars_df)`. Drop the connection before returning.

**Embedding model:** OpenAI `text-embedding-3-small` (1536 dimensions). API key from `OPENAI_API_KEY`. Batch all source texts in a single embeddings API call (max 2048 inputs per call).

**Relevance scoring:** Cosine similarity between the source `cleaned_content` embedding and the session `question` embedding. Stored as `sources.relevance_score`.

**Entity extraction:** Lightweight regex + spaCy `en_core_web_sm` NER. Extract entities of types: `ORG`, `PERSON`, `GPE`, `PRODUCT`, `MONEY`, `DATE`. Store as `[{"type": "ORG", "value": "Acme Corp"}, ...]` in `sources.entities`.

**Input (from pipeline context):**
```python
{
    "session_id": uuid.UUID,
    "question": str,
    "source_ids": list[uuid.UUID],
    "source_count": int,
}
```

**Output (merged into pipeline context):**
```python
{
    "processed_source_ids": list[uuid.UUID],  # sources with non-null relevance_score
    "top_sources": list[uuid.UUID],           # top 20 source IDs by relevance_score DESC
    "qdrant_indexed_count": int,              # number of embeddings upserted to Qdrant
}
```

**Events emitted:**

| event_type | payload keys | description |
|---|---|---|
| `agent_started` | `{"agent": "etl", "source_count": int}` | Before loading sources |
| `etl_progress` | `{"step": "dedup"\|"score"\|"entities"\|"embed"\|"qdrant", "count": int}` | After each pipeline step |
| `agent_completed` | `{"agent": "etl", "processed": int, "indexed": int}` | After Qdrant upsert |
| `agent_failed` | `{"agent": "etl", "error": str}` | Before raising AgentFatalError |

---

### Agent 4 — Writer

**Class:** `backend/app/agents/writer.py::WriterAgent`
**agent_type value:** `"writer"`

**Responsibility:** Produce a structured markdown intelligence report. The Writer performs a RAG retrieval pass (query Qdrant with the session question embedding, retrieve top-20 chunks), constructs a prompt with retrieved source excerpts, calls the LLM (`claude-3-5-sonnet-20241022`), and streams the response. Each streamed chunk is emitted as a `report_chunk` event. The final complete report is written to `research_sessions.report_markdown`.

**Report structure (sections, in order):**
1. Executive Summary (2–3 paragraphs)
2. Key Findings (3–7 bullet points)
3. Detailed Analysis (one H2 section per Planner sub-task)
4. Sources (numbered list with URL, title, and one-line description)

**Citation format:** Inline superscript numbers `[^1]` linking to the Sources section. Every factual claim requires at least one citation. The LLM is instructed to cite source numbers; post-processing validates that all cited numbers exist in the Sources list.

**Input (from pipeline context):**
```python
{
    "session_id": uuid.UUID,
    "question": str,
    "sub_tasks": list[str],
    "top_sources": list[uuid.UUID],
    "processed_source_ids": list[uuid.UUID],
}
```

**Output (merged into pipeline context):**
```python
{
    "report_markdown": str,       # complete markdown report
    "citation_count": int,        # number of distinct sources cited
    "word_count": int,
}
```

**Events emitted:**

| event_type | payload keys | description |
|---|---|---|
| `agent_started` | `{"agent": "writer"}` | Before RAG retrieval |
| `agent_completed` | `{"agent": "writer", "word_count": int, "citation_count": int}` | After final report written to DB |
| `report_chunk` | `{"chunk": str, "chunk_index": int}` | Each streamed LLM response chunk (delta text) |
| `done` | `{"session_id": str, "word_count": int}` | Final event — signals SSE stream close |
| `agent_failed` | `{"agent": "writer", "error": str}` | Before raising AgentFatalError |

---

### SSE event wire format

All events published to Redis pub/sub channel `meridian:session:{uuid}` use this JSON format:

```json
{
  "id": "42",
  "event": "agent_event",
  "data": {
    "agent_type": "web_search",
    "event_type": "sub_task_completed",
    "sequence_number": 42,
    "timestamp": "2026-01-15T10:23:44.123Z",
    "payload": {
      "sub_task_index": 2,
      "source_count": 8,
      "status": "ok",
      "error": null
    }
  }
}
```

The SSE endpoint formats this as:
```
id: 42
event: agent_event
data: {"agent_type":"web_search","event_type":"sub_task_completed","sequence_number":42,"timestamp":"2026-01-15T10:23:44.123Z","payload":{"sub_task_index":2,"source_count":8,"status":"ok","error":null}}

```
(Two newlines terminate each SSE event.)

The `done` event uses `event_type: "done"` and is the signal for the browser `EventSource` to close the connection. The FastAPI SSE handler closes the response after forwarding the `done` event.

---

### Pipeline runner contract

**File:** `backend/app/pipeline/runner.py`

```python
async def run_pipeline(session: ResearchSession, emitter: EventEmitter) -> None:
    """
    Execute the four-agent pipeline for a session.
    Updates research_sessions.status throughout.
    On any AgentFatalError: sets status='failed', error_message, emits error event.
    On successful completion: sets status='completed', report_markdown.
    """
```

The runner is responsible for:
1. Setting `research_sessions.status = 'running'` before the first agent.
2. Constructing the initial pipeline context from the session row.
3. Calling each agent's `run(context)` and merging returned dict into context.
4. Setting `research_sessions.status = 'completed'` and `report_markdown` after the Writer.
5. Catching `AgentFatalError` at any stage, setting `status = 'failed'`, and emitting an `error` event with `payload: {"error": str(exc), "agent": agent_type}`.
6. Never swallowing exceptions silently — all errors must result in a status update and an emitted event.

## Implementation notes

- All agent classes live in `backend/app/agents/`. The `__init__` signature is fixed: `(session_id: uuid.UUID, emitter: EventEmitter)`. The pipeline runner injects the emitter.
- The `EventEmitter` implementation lives in `backend/app/services/emitter.py`. It accepts an async DB session and an async Redis client as constructor arguments.
- Agent unit tests mock the `EventEmitter` with a `FakeEmitter` that appends emitted events to a list for assertion. Tests do not require a running Redis or PostgreSQL instance.
- LLM API keys: `OPENAI_API_KEY` (ETL embeddings), `ANTHROPIC_API_KEY` (Planner and Writer). Both are required at startup; the application fails to start if either is absent.
- The Planner and Writer agents use the `anthropic` Python SDK (async client). The ETL agent uses `openai` Python SDK (async client) for embeddings only.
- The `report_chunk` event payload `chunk` field contains raw delta text from the LLM stream — it is not a complete sentence or paragraph. The frontend accumulates chunks and renders the concatenated result progressively.

## Consequences

**Positive:**
- The `ResearchAgent` ABC enforces a single entry point (`run`) and a consistent event emission pattern across all agents, making the pipeline runner generic.
- Mocking `EventEmitter` decouples agent logic tests from infrastructure, enabling fast unit tests.
- Strict `payload` schemas per event type mean the frontend can deserialize events with a discriminated union type and never encounter unexpected keys.
- Agent outputs are plain dicts merged into a context dict — no shared mutable state, no circular dependencies between agents.

**Negative / trade-offs:**
- Sequential agent execution means total latency is the sum of all four agent durations. Parallelism within WebSearch (across sub-tasks) mitigates this for the slowest phase. Writer parallelism is not possible given its dependency on ETL output.
- The LLM provider split (Anthropic for Planner/Writer, OpenAI for embeddings) requires two API credentials and two SDK clients. This is the optimal cost/quality split for Milestone 1; consolidation to a single provider is a future decision.

**Risks:**
- LLM output parsing in the Planner (sub-task list extraction) is brittle if the model returns malformatted responses. The Planner must implement retry logic (up to 2 retries with a stricter prompt) before raising `AgentFatalError`.
- Qdrant unavailability will fail the ETL agent. The ETL agent must attempt the Qdrant upsert last, after all PostgreSQL writes succeed, so that a Qdrant failure leaves a recoverable state (sources are in PostgreSQL, embeddings can be recomputed).
