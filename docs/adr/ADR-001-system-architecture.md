# ADR-001: System Architecture Overview

## Status
Accepted

## Context
Meridian Research is an autonomous market intelligence SaaS. A user submits a natural-language business research question; the platform orchestrates a team of AI agents to plan, research, process, and synthesize a cited intelligence report. The system must handle long-running async workflows (research can take 30–120 seconds), stream live progress to the frontend, and remain stateless at the backend process level so it scales horizontally on Railway.

Milestone 1 excludes auth (Supabase Auth), payments (Stripe), and the CV pipeline (YOLOv8). All Milestone 1 endpoints are unauthenticated. The architecture must accommodate these additions in later milestones without structural changes.

Constraints:
- Railway backend: stateless processes, no persistent local disk
- Vercel frontend: SSR + static, no WebSocket support in edge functions (SSE is fine)
- Supabase PostgreSQL: all durable state
- Redis: ephemeral coordination state only (task queues, pub/sub for SSE fanout)
- Qdrant: vector embeddings for RAG retrieval
- DuckDB: in-process analytical workloads (not a persistent service)

## Decision

**Request lifecycle:**

1. The frontend (Next.js 14) POSTs to `POST /api/research/create` with a research question.
2. The FastAPI backend validates the request, creates a `research_sessions` row in PostgreSQL with status `queued`, and enqueues a Redis task with the session UUID as the payload. The endpoint returns the session UUID immediately (HTTP 202).
3. A background asyncio worker (running in the same Railway process as FastAPI, started at application startup via `asyncio.create_task`) dequeues the session UUID from Redis and drives the agent pipeline.
4. The agent pipeline runs four agents in sequence: Planner → WebSearch → ETL → Writer. Each agent writes `agent_events` rows to PostgreSQL and publishes SSE-formatted messages to a Redis pub/sub channel keyed by `session_id`.
5. The frontend opens `GET /api/research/{session_id}/stream` immediately after receiving the session UUID. This SSE endpoint subscribes to the Redis pub/sub channel for that session and forwards all published messages to the browser in real time.
6. When the Writer agent finishes, it writes the final markdown report to `research_sessions.report_markdown` and publishes a terminal `done` event. The backend closes the SSE connection. The frontend renders the report.

**Agent pipeline (sequential within a session):**

```
Planner → WebSearch (parallel sub-tasks) → ETL (DuckDB/Polars) → Writer
```

Each agent is an async Python class implementing the `ResearchAgent` interface defined in ADR-003. Agents are instantiated per-session and share no mutable state between sessions.

**DuckDB usage:**

DuckDB runs in-process (`:memory:` database, not a file). Each ETL invocation creates a fresh DuckDB connection, loads Polars DataFrames, runs SQL transforms, and discards the connection. DuckDB is never shared across coroutines. This is safe because the background worker runs a single pipeline per session at a time within one asyncio event loop.

**Redis usage:**

- Task queue: a Redis list (`brpoplpush` pattern) holds pending session UUIDs.
- SSE fanout: a Redis pub/sub channel per session (`meridian:session:{uuid}`) carries SSE event strings. The SSE endpoint subscribes and streams to the browser. This decouples the agent pipeline (publisher) from the HTTP connection (subscriber) and allows multiple browser tabs to subscribe to the same session.

**State storage:**

| Data | Store |
|---|---|
| Session metadata and status | Supabase PostgreSQL (`research_sessions`) |
| Discovered sources | Supabase PostgreSQL (`sources`) |
| Agent trace events | Supabase PostgreSQL (`agent_events`) |
| Final report markdown | Supabase PostgreSQL (`research_sessions.report_markdown`) |
| Source text embeddings | Qdrant (collection: `meridian_sources`) |
| Raw analytical data (transient) | DuckDB in-process, discarded after ETL |
| Task queue (transient) | Redis list |
| SSE fanout (transient) | Redis pub/sub |

**Frontend architecture:**

- `/` — research input form. On submit, POSTs to the backend, receives `session_id`, immediately navigates to `/research/[session_id]`.
- `/research/[session_id]` — opens an `EventSource` to the SSE endpoint. Renders a live trace timeline of agent events. When the `done` event arrives, fetches the final report via `GET /api/research/{session_id}` and renders the markdown.

**Inter-service communication:**

All backend-to-Supabase traffic uses the SQLAlchemy 2.0 async engine over the standard PostgreSQL wire protocol. All backend-to-Redis traffic uses `redis.asyncio`. All backend-to-Qdrant traffic uses the `qdrant-client` async Python SDK. The frontend communicates with the backend exclusively via HTTP (REST + SSE). There is no WebSocket, no GraphQL, no gRPC in Milestone 1.

## Implementation notes

**FastAPI application entrypoint:** `backend/app/main.py`

At startup, register the background worker:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(worker.run_forever())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
```

**Worker loop:** `backend/app/services/worker.py`
- `BRPOPLPUSH` on `meridian:queue:sessions` with a 5-second timeout.
- On receiving a session UUID, look up the session in PostgreSQL, instantiate the pipeline, and `await pipeline.run(session)`.
- Catch all exceptions; on failure set `research_sessions.status = 'failed'` and publish an error SSE event.

**Redis key conventions:**
- Task queue list: `meridian:queue:sessions`
- SSE pub/sub channel: `meridian:session:{session_uuid}`

**Environment variables required (all backends):**
- `DATABASE_URL` — async PostgreSQL URL (`postgresql+asyncpg://...`)
- `REDIS_URL` — Redis connection URL (`redis://...`)
- `QDRANT_URL` — Qdrant HTTP URL
- `QDRANT_API_KEY` — Qdrant API key (optional for local dev)

**File layout (backend):**
```
backend/app/
├── main.py                  # FastAPI app, lifespan, router registration
├── api/
│   ├── research.py          # POST /api/research/create, GET /api/research/{id}/stream, GET /api/research/{id}
├── agents/
│   ├── base.py              # ResearchAgent ABC (see ADR-003)
│   ├── planner.py
│   ├── web_search.py
│   ├── etl.py
│   └── writer.py
├── models/
│   └── research.py          # SQLAlchemy ORM models
├── schemas/
│   └── research.py          # Pydantic request/response schemas
├── pipeline/
│   └── runner.py            # Orchestrates agent sequence for a session
└── services/
    ├── worker.py            # Redis consumer loop
    ├── redis_client.py      # Shared async Redis client
    └── db.py                # SQLAlchemy async engine + session factory
```

**Qdrant collection:** `meridian_sources`, vector size 1536 (OpenAI `text-embedding-3-small`), distance: Cosine. Created at application startup if it does not exist.

## Consequences

**Positive:**
- Stateless backend process — horizontally scalable on Railway with no changes.
- SSE over HTTP/1.1 — no WebSocket infrastructure needed; works on Vercel edge for the frontend.
- Redis pub/sub decouples pipeline execution from HTTP connection lifecycle — browser reconnects do not interrupt the running pipeline.
- DuckDB in-process eliminates an external analytical DB dependency; no infra to provision.
- Sequential agent pipeline is simple to reason about and debug; parallelism is limited to within the WebSearch agent across sub-tasks.

**Negative / trade-offs:**
- Single Railway process runs both FastAPI and the background worker. Under high load, long-running agent pipelines compete with HTTP request handling for CPU. Mitigation: Railway allows vertical scaling; process separation is a Milestone 2 concern.
- DuckDB in-memory means analytical data is not persisted. If the process crashes mid-ETL, the session fails and must be retried. This is acceptable for Milestone 1.
- Redis pub/sub has no persistence — if the SSE subscriber connects after the session completes, it will miss all events. Mitigation: the frontend also polls `GET /api/research/{session_id}` on load to check for a completed report.

**Risks:**
- asyncio event loop blocking: any synchronous call inside an agent will block all sessions. All agents must use `await` for every I/O call. Enforce via code review.
- Redis unavailability will prevent new sessions from starting. Implement a startup health check that fails fast if Redis is unreachable.
