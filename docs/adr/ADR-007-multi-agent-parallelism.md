# ADR-007: Multi-Agent Parallelism Design

**Status:** Accepted
**Date:** 2026-04-29
**Deciders:** PM Agent, Backend Agent
**Milestone:** 4 — Multi-agent expansion

---

## Context

Milestone 3 delivered a two-agent research pipeline: WebSearchAgent and CvDocumentAgent
ran in parallel via `asyncio.gather`, and WriterAgent ran sequentially after both
completed. Milestone 4 adds two more research agents (NewsAgent, StructuredDataAgent)
and a post-write CriticAgent. This ADR documents the parallelism strategy, merge
contract, error handling, timeouts, and session state machine that govern these six
agents.

### Forces

- **Latency**: A typical research session should complete in under 3 minutes. Running
  4 research agents sequentially at ~30s each would consume 2 minutes before writing
  even begins. Parallelism is mandatory.
- **Partial failure tolerance**: News and EDGAR data are enrichment sources — their
  absence must not abort a session that has good web search results.
- **Output heterogeneity**: Each research agent returns a different output schema.
  WriterAgent needs a single merged input dict.
- **Critic placement**: Fact-checking is only meaningful after the report exists.
  CriticAgent must run sequentially after WriterAgent.

---

## Decision

Run all four research agents concurrently via `asyncio.gather(..., return_exceptions=True)`,
with individual `asyncio.wait_for` timeouts. Merge outputs into a unified dict before
passing to WriterAgent. Run CriticAgent sequentially after WriterAgent. Treat all
research-agent and critic failures as non-fatal.

---

## Architecture

### Agent roster

| Agent | Type | Phase | Fatal on error? | Output key(s) |
|---|---|---|---|---|
| PlannerAgent | Sequential (pre-research) | Planning | Yes (AgentFatalError) | sub_tasks |
| WebSearchAgent | Parallel research | Research | Yes (AgentFatalError) | source_ids, sources_count |
| CvDocumentAgent | Parallel research | Research | No (AgentError, non-fatal) | chart_results, chart_count |
| NewsAgent | Parallel research | Research | No (AgentError, non-fatal) | news_source_ids, news_count |
| StructuredDataAgent | Parallel research | Research | No (AgentError, non-fatal) | edgar_source_ids, edgar_count |
| WriterAgent | Sequential (post-research) | Writing | Yes (AgentFatalError) | report_markdown |
| CriticAgent | Sequential (post-write) | Review | No (AgentError, non-fatal) | quality_score, flagged_claims |

**WebSearchAgent is the only fatal research agent.** If web search fails, there is no
usable content to write a report from. All enrichment agents (CV, News, EDGAR, Critic)
are non-fatal: their failure produces a degraded but valid output.

### Execution flow (ASCII)

```
User submits question
        │
        ▼
  PlannerAgent ──────────────────────► sub_tasks (list[str])
        │
        ▼
  asyncio.gather (timeout=120s each)
  ┌─────────────────────────────────────────────────┐
  │  WebSearchAgent    CvDocumentAgent              │
  │  NewsAgent         StructuredDataAgent          │
  └─────────────────────────────────────────────────┘
        │
        ▼
  _merge_research_results(results)
  ──► {sources, chart_results, news_source_ids, edgar_source_ids}
        │
        ▼
  WriterAgent ────────────────────────► report_markdown
        │
        ▼
  QualityScorer ──────────────────────► ReportQuality (sync, no LLM)
        │
        ▼
  CriticAgent ────────────────────────► {quality_score, flagged_claims}
        │
        ▼
  ResearchSession.status = "completed"
  Emit: report_complete, report_quality, report_critique
```

---

## Agent execution detail

### Parallel research phase

```python
async def _run_research_agents(
    session_id: uuid.UUID,
    emitter: EventEmitter,
    db: AsyncSession,
    planner_output: dict[str, Any],
    settings: Settings,
) -> list[dict[str, Any] | BaseException]:
    agents = [
        WebSearchAgent(session_id, emitter, db, ...),
        CvDocumentAgent(session_id, emitter, db,
                        modal_base_url=settings.modal_base_url,
                        modal_api_secret=settings.modal_api_secret),
        NewsAgent(session_id, emitter, db,
                  newsapi_key=settings.newsapi_key,
                  gnews_key=settings.gnews_key),
        StructuredDataAgent(session_id, emitter, db),
    ]

    async def _run_with_timeout(agent: ResearchAgent) -> dict[str, Any]:
        return await asyncio.wait_for(
            agent.run(planner_output),
            timeout=120.0,
        )

    return await asyncio.gather(
        *[_run_with_timeout(a) for a in agents],
        return_exceptions=True,
    )
```

### Result merge strategy

Each agent returns a dict or raises an exception (captured by `return_exceptions=True`).
The merge function collects successful results and logs failures:

```python
def _merge_research_results(
    results: list[dict[str, Any] | BaseException],
    agent_names: list[str],
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "chart_results": [],
        "news_source_ids": [],
        "edgar_source_ids": [],
    }
    agents_succeeded = 0
    agents_failed = 0

    for name, result in zip(agent_names, results):
        if isinstance(result, BaseException):
            logger.warning("research_agent_failed", agent=name, error=str(result))
            agents_failed += 1
        else:
            merged.update(result)  # each agent owns distinct keys, no collision
            agents_succeeded += 1

    merged["_meta"] = {
        "agents_succeeded": agents_succeeded,
        "agents_failed": agents_failed,
    }
    return merged
```

**Key invariant**: each agent's output dict uses distinct top-level keys. There are no
collisions in the merge — `chart_results` (CV), `news_source_ids` (News),
`edgar_source_ids` (EDGAR), and `source_ids` (Web) are all separate keys.

---

## Agent output schemas

### WebSearchAgent
```python
{
    "source_ids": list[uuid.UUID],
    "sources_count": int,
    "sub_tasks": list[str],
}
```

### CvDocumentAgent
```python
{
    "chart_results": list[dict],   # ChartResult.model_dump() per chart
    "chart_count": int,
}
```

### NewsAgent
```python
{
    "news_source_ids": list[uuid.UUID],
    "news_count": int,
}
```

### StructuredDataAgent
```python
{
    "edgar_source_ids": list[uuid.UUID],
    "edgar_count": int,
    "edgar_companies": list[str],
}
```

### WriterAgent input (merged)
```python
{
    "question": str,
    "sub_tasks": list[str],
    "chart_results": list[dict],          # from CV agent (default [])
    "news_source_ids": list[uuid.UUID],   # from News agent (default [])
    "edgar_source_ids": list[uuid.UUID],  # from EDGAR agent (default [])
}
```
WriterAgent loads all Source rows for the session from the database, so it does not
need the raw source content in the merged dict — only hints about which sources exist.

### CriticAgent input
```python
{
    "report_markdown": str,
    "sources": list[{"url": str, "title": str, "content": str}],
}
```

---

## Error handling matrix

| Agent | Error type | Handling | Session outcome |
|---|---|---|---|
| PlannerAgent | AgentFatalError | Worker catches, session → failed | Aborted |
| WebSearchAgent | AgentFatalError | Worker catches, session → failed | Aborted |
| WebSearchAgent | asyncio.TimeoutError | Treated as AgentFatalError | Aborted |
| CvDocumentAgent | AgentError | Logged, chart_results=[] | Continues (text-only) |
| CvDocumentAgent | asyncio.TimeoutError | Logged, chart_results=[] | Continues |
| NewsAgent | AgentError | Logged, news_count=0 | Continues |
| NewsAgent | asyncio.TimeoutError | Logged, news_count=0 | Continues |
| StructuredDataAgent | AgentError | Logged, edgar_count=0 | Continues |
| StructuredDataAgent | asyncio.TimeoutError | Logged, edgar_count=0 | Continues |
| WriterAgent | AgentFatalError | Worker catches, session → failed | Aborted |
| CriticAgent | AgentError | Logged, quality_score=1.0 | Continues (no critique) |
| CriticAgent | asyncio.TimeoutError | Logged, quality_score=1.0 | Continues |

**WebSearchAgent timeout**: WebSearchAgent is wrapped in `asyncio.wait_for` like the
other agents, but a TimeoutError is re-raised as `AgentFatalError` since there is no
usable content without web search results.

---

## Session state machine

```
pending ──► in_progress ──► writing ──► reviewing ──► completed
                │                                         ▲
                └──────────────────── failed ─────────────┘
                  (on PlannerAgent,
                   WebSearchAgent, or
                   WriterAgent fatal error)
```

| State | Description | Next states |
|---|---|---|
| `pending` | Session created, worker not yet assigned | `in_progress` |
| `in_progress` | Planner + research agents running | `writing`, `failed` |
| `writing` | WriterAgent active | `reviewing`, `failed` |
| `reviewing` | CriticAgent + QualityScorer active | `completed`, `failed` |
| `completed` | Report stored, critique stored | — |
| `failed` | Fatal error occurred | — |

State is stored in `research_sessions.status` (VARCHAR). Transitions are written by
the research worker. The SSE stream endpoint reads this field to know when to close.

---

## Timeouts

| Agent | Timeout | Rationale |
|---|---|---|
| PlannerAgent | 30s | LLM call with small output |
| WebSearchAgent | 120s | Up to 50 web pages scraped concurrently |
| CvDocumentAgent | 120s | Modal cold-start + classify + extract per image |
| NewsAgent | 30s | Two simple REST API calls |
| StructuredDataAgent | 60s | EDGAR full-text search + XBRL companyfacts |
| WriterAgent | 90s | LLM call with large context (30 sources) |
| CriticAgent | 60s | LLM call with report + source summaries |

---

## News API selection

Two news feed APIs are integrated:

| API | Endpoint | Free tier | Key env var |
|---|---|---|---|
| NewsAPI | `newsapi.org/v2/everything` | 100 req/day, 1-month history | `NEWSAPI_KEY` |
| GNews | `gnews.io/api/v4/search` | 100 req/day, 3-day history | `GNEWS_KEY` |

Both APIs are called concurrently within NewsAgent. GNews provides more recent news
(3-day window) while NewsAPI provides broader historical coverage (1 month). Results
from both are de-duplicated by URL before storage.

If either key is missing, that API is skipped silently. If both keys are missing,
NewsAgent returns empty results without raising.

---

## Structured data: SEC EDGAR XBRL

The SEC provides a free, unauthenticated XBRL data API:

- **Company search**: `https://efts.sec.gov/LATEST/search-index?q={query}&dateRange=custom&startdt=2023-01-01`
- **Company facts**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`

The agent extracts the CIK from search results, then fetches the companyfacts JSON
and pulls `us-gaap` metrics for the 4 most recent periods.

Rate limit: EDGAR requests a `User-Agent` header identifying the application. The
agent sets: `User-Agent: Meridian Research contact@meridianresearch.com`.

---

## Consequences

### Positive

- Research phase latency: ~30s (parallel) vs ~210s (sequential for 4 agents)
- Non-fatal enrichment agents mean sessions succeed even when EDGAR or news APIs are
  rate-limited or unreachable
- CriticAgent provides a quality signal without blocking report delivery
- State machine makes it easy to add new agents in future milestones

### Negative / trade-offs

- `asyncio.gather(return_exceptions=True)` requires explicit handling of each result
  type (`BaseException`, `AgentFatalError`, `dict`) — easy to accidentally swallow errors
- WebSearchAgent is fatally coupled to session success. If NewsAPI were the primary
  source this would need revisiting.
- EDGAR rate limits (10 req/10s) may be hit for batch jobs. A simple `asyncio.sleep(1)`
  between companyfacts requests mitigates this at the cost of slight latency.
- CriticAgent adds ~30–60s to session time. This is acceptable given the 3-minute
  budget but must be monitored if the budget tightens.

---

## Related decisions

- ADR-005: CV pipeline architecture — CvDocumentAgent design
- ADR-004: DuckDB/Polars ETL pipeline — source storage schema
- ADR-001: FastAPI async architecture — async-first session handling
