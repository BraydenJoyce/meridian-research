# ADR-004: Production Pipeline Architecture — Qdrant Schema, RAG Design, Benchmark Approach

## Status
Accepted

## Context
Milestone 2 upgrades the ETL component from a single monolithic `ETLAgent` (as defined in ADR-003) into a standalone, production-grade pipeline module at `backend/app/pipeline/`. The upgrade is driven by three requirements:

1. **Cost and dependency reduction.** The Milestone 1 ETL agent uses OpenAI `text-embedding-3-small` (1536-dim vectors) for embeddings. For Milestone 2, all embedding work moves to `sentence-transformers/all-MiniLM-L6-v2` (384-dim vectors), eliminating the OpenAI dependency from the pipeline entirely and removing per-token embedding costs.

2. **Pipeline decomposition.** The single ETL step becomes five discrete, independently testable stages: Ingest → Deduplicate → Score → Extract entities → Index. Each stage has a defined input contract, output contract, and structured log record.

3. **RAG context injection for the Planner.** The `PlannerAgent` must retrieve prior relevant sources before generating its sub-task plan, so that research on related topics is not duplicated and context from previous sessions informs the plan. A new `rag_service.py` handles this retrieval.

This ADR also covers the Qdrant collection schema change required by the embedding model switch (from `meridian_sources` / 1536-dim as defined in ADR-001 to `research_sources` / 384-dim), the structured logging contract all five pipeline stages must satisfy, and the benchmark methodology for validating the 1000-source / 60-second performance target.

**Constraints inherited from prior ADRs:**
- DuckDB runs in-process (`:memory:`), one connection per pipeline invocation, discarded after (ADR-001).
- Qdrant client is the async Python SDK; all Qdrant calls are `await`-ed (ADR-001).
- The `PlannerAgent` receives `session_id`, `question`, and `created_at` as input context (ADR-003).
- structlog is the logging library throughout the backend.

---

## Decision

### 1. Qdrant Collection Schema

#### Collection name and vector configuration

| Parameter | Value |
|---|---|
| Collection name | `research_sources` |
| Vector size | `384` |
| Distance metric | `Cosine` |
| On-disk payload storage | `true` (payload stored on disk, not in RAM) |
| HNSW `m` | `16` |
| HNSW `ef_construct` | `100` |

The collection `meridian_sources` defined in ADR-001 (1536-dim, OpenAI embeddings) remains in place for Milestone 1 sessions and is not migrated. `research_sources` is a new collection created at application startup if it does not exist. Both collections coexist during the Milestone 2 transition period.

#### Payload schema

Every point upserted into `research_sources` carries the following payload fields. All fields are present on every point — none are optional.

| Field | Qdrant payload type | Source | Description |
|---|---|---|---|
| `source_id` | `keyword` | `sources.id` (UUID string) | PostgreSQL primary key of the source row |
| `session_id` | `keyword` | `sources.session_id` (UUID string) | Research session that produced this source |
| `url` | `keyword` | `sources.url` | Exact source URL |
| `domain` | `keyword` | `sources.domain` | Registered domain (e.g. `reuters.com`) |
| `title` | `text` | `sources.title` | Page title; empty string `""` if NULL |
| `sub_task_index` | `integer` | `sources.sub_task_index` | Planner sub-task that produced this source (0-based) |
| `relevance_score` | `float` | `sources.relevance_score` | ETL quality score 0.0–1.0 |
| `entity_types` | `keyword[]` | derived from `sources.entities` | Flat list of entity type strings present in source (e.g. `["ORG", "PERSON"]`) |
| `chunk_index` | `integer` | pipeline computed | Position of this chunk within the source document (0-based; 0 for non-chunked sources) |
| `chunk_count` | `integer` | pipeline computed | Total number of chunks for this source |
| `indexed_at` | `datetime` | pipeline computed | ISO-8601 UTC timestamp of Qdrant upsert |

#### Payload indexes (for filtered search)

The following payload fields are indexed to enable filtered vector search. Unindexed fields can still be stored in payload but cannot be used in search filters efficiently.

| Field | Index type | Rationale |
|---|---|---|
| `session_id` | `keyword` | Isolate RAG retrieval to sources from prior sessions (exclude the current session) |
| `domain` | `keyword` | Filter by source domain (e.g. exclude social media, include only news) |
| `relevance_score` | `float` | Range filter to exclude low-quality sources (score < 0.3) |
| `entity_types` | `keyword` | Filter to sources mentioning specific entity types |
| `indexed_at` | `datetime` | Time-range filtering for recency |

#### Qdrant collection creation (startup)

The collection is created at application startup by `backend/app/services/qdrant_client.py`:

```python
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    VectorParams, Distance, HnswConfigDiff,
    PayloadSchemaType, TokenizerType,
)

async def ensure_collection(client: AsyncQdrantClient) -> None:
    collections = await client.get_collections()
    names = {c.name for c in collections.collections}
    if "research_sources" not in names:
        await client.create_collection(
            collection_name="research_sources",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
            on_disk_payload=True,
        )
        # Create payload indexes
        await client.create_payload_index(
            collection_name="research_sources",
            field_name="session_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            collection_name="research_sources",
            field_name="domain",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            collection_name="research_sources",
            field_name="relevance_score",
            field_schema=PayloadSchemaType.FLOAT,
        )
        await client.create_payload_index(
            collection_name="research_sources",
            field_name="entity_types",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            collection_name="research_sources",
            field_name="indexed_at",
            field_schema=PayloadSchemaType.DATETIME,
        )
```

---

### 2. Embedding Model and Chunking Strategy

**Embedding model:** `sentence-transformers/all-MiniLM-L6-v2`
- Output dimensions: 384
- Max input tokens: 512 (hard limit of the model)
- Inference: local, CPU-feasible for batch sizes up to 512 documents; no API call, no network dependency
- License: Apache 2.0
- Library: `sentence-transformers>=2.7.0`

**Chunking strategy:**

Source documents longer than 512 tokens are split into overlapping chunks before embedding. Documents at or below 512 tokens are embedded as a single chunk.

| Parameter | Value | Rationale |
|---|---|---|
| Chunk size | 512 tokens | Matches model max input; maximises semantic density per vector |
| Overlap | 64 tokens | Preserves sentence continuity across chunk boundaries |
| Tokenizer | `transformers` `AutoTokenizer` for `sentence-transformers/all-MiniLM-L6-v2` | Exact token count for the model |
| Minimum chunk length | 50 tokens | Chunks shorter than 50 tokens are discarded (navigation artifacts, boilerplate) |
| Splitting boundary | Sentence boundary within the 512-token window | Prefer not to cut mid-sentence; fall back to token boundary if no sentence end found |

Each chunk produces one Qdrant point. The `chunk_index` payload field identifies chunk position; `chunk_count` identifies total chunks for the source. For retrieval, the top-k search returns chunk-level points; the `source_id` payload field is used to deduplicate to unique sources.

**Batch embedding:** All chunks for a pipeline run are embedded in a single `model.encode()` call with `batch_size=64`, `show_progress_bar=False`, `normalize_embeddings=True`. Normalisation to unit length means dot product equals cosine similarity, which is consistent with the Qdrant Cosine distance metric.

---

### 3. RAG Retrieval Design

**File:** `backend/app/services/rag_service.py`

**Call site:** `PlannerAgent.run()`, immediately before the LLM call. The retrieved context is injected into the Planner's system prompt.

#### Query strategy

```
question (str)
  → embed with all-MiniLM-L6-v2 → query_vector (384-dim, normalised)
  → Qdrant search on collection "research_sources"
      filter: session_id NOT IN [current_session_id]
      filter: relevance_score >= 0.30
      top_k: 20
      score_threshold: 0.45
  → deduplicate to unique source_ids (keep highest-scoring chunk per source)
  → return top 10 unique sources by score DESC
```

| Parameter | Value | Rationale |
|---|---|---|
| `top_k` (chunks) | 20 | Cast a wide net; deduplication reduces this to ≤ 10 unique sources |
| Score threshold | 0.45 | Cosine similarity ≥ 0.45 indicates meaningful topical overlap; below this threshold sources are noise |
| Relevance score filter | ≥ 0.30 | Exclude low-quality sources that passed chunking but scored poorly in ETL quality scoring |
| Unique sources returned | ≤ 10 | Caps context injection to stay within Planner token budget |
| Exclude current session | yes | Prevents the current session's own in-progress sources from appearing as prior context |

#### Graceful degradation

If Qdrant returns zero results above the score threshold (cold start, no prior sessions, or entirely novel topic), `rag_service.get_context()` returns `None`. The `PlannerAgent` detects `None` and proceeds without injecting any prior context — the system prompt omits the context block entirely. This is the expected behaviour for the first query on any new topic.

If the Qdrant client raises a connection error, `rag_service.get_context()` logs the error via structlog at `warning` level, then returns `None` (same as no-results path). The Planner proceeds without context rather than failing the session.

#### Context formatting for the Planner

When context is available, the following block is prepended to the Planner's system prompt, before the main planning instructions:

```
--- PRIOR RESEARCH CONTEXT ---
The following {n} sources from prior research sessions are relevant to this question.
Use them to avoid re-investigating known facts and to identify gaps.

[1] {title} ({domain})
    URL: {url}
    Relevance: {relevance_score:.2f}
    Excerpt: {chunk_text[:300]}...

[2] ...

--- END PRIOR RESEARCH CONTEXT ---
```

**Token budget for context block:** Maximum 1,500 tokens. Each source entry is truncated to 300 characters of `chunk_text`. If 10 sources × ~120 tokens/entry exceeds the budget, sources are dropped from the bottom (lowest score) until the budget is satisfied.

**Injection position:** The context block is the first content in the system prompt, before the main instructions. This positions it as background knowledge the model should factor into its planning, not as instructions to follow.

#### `rag_service.get_context` signature

```python
from dataclasses import dataclass

@dataclass
class RagSource:
    source_id: str        # UUID string matching sources.id
    session_id: str       # UUID string of the originating session
    title: str
    url: str
    domain: str
    relevance_score: float
    chunk_text: str       # text of the highest-scoring chunk for this source
    score: float          # Qdrant cosine similarity score

async def get_context(
    question: str,
    current_session_id: str,
    *,
    top_k_chunks: int = 20,
    score_threshold: float = 0.45,
    min_relevance_score: float = 0.30,
    max_sources: int = 10,
) -> list[RagSource] | None:
    """
    Embed question, query research_sources, deduplicate to unique sources.
    Returns list of RagSource (length 1–max_sources) or None if no results
    above threshold or if Qdrant is unreachable.
    """
```

---

### 4. Structured Logging Contract

All five pipeline stages must emit exactly one structured log record on completion. This record is emitted via structlog and also written to a structured pipeline log for observability dashboards.

#### TypedDict definition

**File:** `backend/app/pipeline/log_schema.py`

```python
from typing import TypedDict, Optional


class PipelineStageLog(TypedDict):
    """
    Structured log record emitted by each pipeline stage on completion.
    All five stages (ingest, deduplicate, score, extract_entities, index)
    must emit exactly one record of this type.

    Emit via:
        import structlog
        log = structlog.get_logger()
        log.info("pipeline_stage_complete", **stage_log)
    """
    stage_name: str
    """One of: 'ingest', 'deduplicate', 'score', 'extract_entities', 'index'"""

    session_id: str
    """UUID string of the research session being processed."""

    records_in: int
    """Number of records received as input to this stage."""

    records_out: int
    """Number of records passed to the next stage (after filtering/deduplication)."""

    records_dropped: int
    """Number of records that did not pass through. Must equal records_in - records_out."""

    drop_reason: Optional[str]
    """
    Human-readable summary of why records were dropped.
    None if records_dropped == 0.
    Examples: 'duplicate_url', 'below_quality_threshold', 'chunk_too_short',
              'qdrant_upsert_failed', 'empty_content'
    If multiple reasons apply, use the most prevalent reason with a count suffix,
    e.g. 'duplicate_url (12), empty_content (3)'.
    """

    duration_ms: float
    """Wall-clock time for this stage in milliseconds (time.perf_counter() delta * 1000)."""

    extra: Optional[dict]
    """
    Stage-specific additional fields. Optional. Not required for contract compliance.
    Examples:
      ingest:           {'source_count_from_db': int}
      deduplicate:      {'minhash_threshold': float, 'lsh_bands': int}
      score:            {'mean_score': float, 'median_score': float}
      extract_entities: {'entity_count': int, 'model': str}
      index:            {'collection': str, 'batch_size': int, 'chunks_per_source_mean': float}
    """
```

#### Stage-to-field mapping

| Stage | `stage_name` | `records_in` | `records_out` | `records_dropped` | Typical `drop_reason` |
|---|---|---|---|---|---|
| Ingest | `"ingest"` | Sources fetched from PostgreSQL | Sources with non-null `cleaned_content` | Sources with null content | `"empty_content"` |
| Deduplicate | `"deduplicate"` | Sources entering dedup | Sources surviving dedup | Near-duplicate sources removed | `"duplicate_url"` or `"near_duplicate_minhash"` |
| Score | `"score"` | Sources entering scoring | Sources with `relevance_score >= 0.30` | Sources below quality threshold | `"below_quality_threshold"` |
| Extract entities | `"extract_entities"` | Sources entering NER | Sources with entity extraction completed | Sources where NER failed | `"ner_error"` |
| Index | `"index"` | Chunks submitted for Qdrant upsert | Chunks successfully upserted | Chunks that failed upsert | `"qdrant_upsert_failed"` |

#### Validation

The pipeline runner validates each emitted `PipelineStageLog` before logging:

```python
def validate_stage_log(log: PipelineStageLog) -> None:
    assert log["records_dropped"] == log["records_in"] - log["records_out"], (
        f"Stage {log['stage_name']}: records_in({log['records_in']}) - "
        f"records_out({log['records_out']}) != records_dropped({log['records_dropped']})"
    )
    assert log["drop_reason"] is None or log["records_dropped"] > 0, (
        f"Stage {log['stage_name']}: drop_reason set but records_dropped == 0"
    )
    assert log["duration_ms"] >= 0.0
    assert log["stage_name"] in {
        "ingest", "deduplicate", "score", "extract_entities", "index"
    }
```

---

### 5. Benchmark Methodology

**Target:** Full pipeline (all 5 stages) processes 1,000 synthetic sources in under 60.0 seconds on CI hardware (2 vCPU, 4 GB RAM, no GPU).

#### Dataset

- **Size:** 1,000 synthetic source records
- **Near-duplicate rate:** ~20% (200 sources are near-duplicates of existing sources, varied by minor paraphrasing to test MinHash LSH)
- **Content length distribution:** 200–2,000 words per source (uniform random), targeting a mean of ~900 words (~1,200 tokens before chunking)
- **Generation:** `backend/tests/fixtures/generate_benchmark_sources.py` — deterministic, seeded with `random.seed(42)` for reproducibility. Generates realistic-looking but synthetic market intelligence text.

#### Infrastructure

- **DuckDB:** In-memory (`:memory:`), as per production configuration.
- **Qdrant:** Mocked with `unittest.mock.AsyncMock`. The mock records call counts and argument sizes but performs no network I/O. This isolates pipeline CPU/memory performance from network latency.
- **PostgreSQL:** Mocked with a `FakeSourceRepository` that returns the benchmark dataset from memory.
- **Embedding model:** Real `all-MiniLM-L6-v2` model loaded once per benchmark run; no mocking. Embedding is the dominant CPU cost and must be measured accurately.

#### Timing approach

```python
import time

stage_timings: dict[str, float] = {}

for stage_name, stage_fn in pipeline_stages:
    t0 = time.perf_counter()
    await stage_fn(records)
    stage_timings[stage_name] = (time.perf_counter() - t0) * 1000  # milliseconds

total_ms = sum(stage_timings.values())
```

`time.perf_counter()` is used exclusively — not `time.time()` or `datetime.now()`. Each stage is timed independently; the total is the sum of per-stage times (no wall-clock measurement of the whole run, to avoid including fixture setup time).

#### Success criteria

| Criterion | Pass condition |
|---|---|
| Total pipeline time | `total_ms < 60_000` |
| Ingest stage | `stage_timings["ingest"] < 5_000` ms |
| Deduplicate stage | `stage_timings["deduplicate"] < 8_000` ms |
| Score stage | `stage_timings["score"] < 10_000` ms |
| Extract entities stage | `stage_timings["extract_entities"] < 20_000` ms |
| Index stage (mock) | `stage_timings["index"] < 5_000` ms |
| Records processed | `records_out["score"] >= 750` (≥75% of 1,000 survive quality scoring) |
| Dedup rate | `records_dropped["deduplicate"]` between 150 and 250 (expected ~20% near-dups) |
| Log contract compliance | All 5 `PipelineStageLog` records pass `validate_stage_log()` |

The per-stage budgets are advisory; only the total `< 60_000 ms` is a hard gate for benchmark pass/fail.

#### Output artifact

On completion, the benchmark writes `backend/tests/benchmark_results.md` with the following required sections:

```markdown
# Pipeline Benchmark Results

**Date:** {ISO-8601 date}
**Commit:** {git SHA}
**Hardware:** {CPU model, RAM, OS}
**Dataset:** 1000 sources, ~20% near-duplicates

## Stage Timings

| Stage | Records In | Records Out | Dropped | Duration (ms) |
|---|---|---|---|---|
| ingest | ... | ... | ... | ... |
| deduplicate | ... | ... | ... | ... |
| score | ... | ... | ... | ... |
| extract_entities | ... | ... | ... | ... |
| index | ... | ... | ... | ... |
| **TOTAL** | | | | **{total}** |

## Pass / Fail

**Result:** PASS / FAIL
**Total duration:** {total_ms:.1f} ms (limit: 60,000 ms)

## Notes

{Any anomalies, bottlenecks, or observations}
```

The benchmark is run as a pytest test (`backend/tests/test_pipeline_benchmark.py`) with the marker `@pytest.mark.benchmark`. It is excluded from the standard test suite (`pytest -m "not benchmark"`) and run explicitly in CI on the `main` branch merge job.

---

## Implementation Notes

**Pipeline module layout:**
```
backend/app/pipeline/
├── __init__.py
├── runner.py              # Orchestrates 5-stage sequence; validates PipelineStageLog per stage
├── stages/
│   ├── __init__.py
│   ├── ingest.py          # Stage 1: load sources from PostgreSQL into DuckDB
│   ├── deduplicate.py     # Stage 2: MinHash LSH (datasketch); threshold=0.85 Jaccard
│   ├── score.py           # Stage 3: 6-factor quality scorer (relevance, freshness, authority, length, entity density, source diversity)
│   ├── extract_entities.py  # Stage 4: spaCy en_core_web_sm; entity types: ORG, PERSON, GPE, PRODUCT, MONEY, DATE
│   └── index.py           # Stage 5: chunk → embed → Qdrant upsert
└── log_schema.py          # PipelineStageLog TypedDict + validate_stage_log()
```

**RAG service layout:**
```
backend/app/services/
└── rag_service.py         # RagSource dataclass + get_context() async function
```

**Embedding model loading:** The model is loaded once at application startup and held in a module-level singleton in `backend/app/services/embedder.py`:

```python
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None

def get_embedder() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model
```

The model is loaded lazily on first call. The `ensure_embedder_loaded()` startup hook calls `get_embedder()` at application startup (inside the `lifespan` context manager in `main.py`) so the first pipeline invocation does not incur model load latency.

**Qdrant point ID generation:** Each chunk's Qdrant point ID is a deterministic UUID v5 derived from `(source_id, chunk_index)`:

```python
import uuid

QDRANT_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID namespace DNS

def chunk_point_id(source_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(QDRANT_NAMESPACE, f"{source_id}:{chunk_index}"))
```

Deterministic IDs make re-indexing idempotent: upserting the same source twice produces the same point ID and overwrites without duplication.

**Environment variables (additions for Milestone 2):**

| Variable | Purpose |
|---|---|
| `QDRANT_URL` | Already defined in ADR-001 |
| `QDRANT_API_KEY` | Already defined in ADR-001 |
| `SENTENCE_TRANSFORMERS_HOME` | Optional; cache directory for model weights (default: `~/.cache/huggingface`) |

No new required environment variables are introduced. The sentence-transformers model is bundled in the Docker image for production (downloaded at image build time, not at runtime).

**Dockerfile change (backend):** Add to `devops/Dockerfile.backend`:
```dockerfile
# Pre-download embedding model weights at build time
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

**structlog integration:** Each stage emits via:
```python
import structlog
log = structlog.get_logger()

# At stage completion:
log.info(
    "pipeline_stage_complete",
    stage_name=stage_log["stage_name"],
    session_id=stage_log["session_id"],
    records_in=stage_log["records_in"],
    records_out=stage_log["records_out"],
    records_dropped=stage_log["records_dropped"],
    drop_reason=stage_log["drop_reason"],
    duration_ms=stage_log["duration_ms"],
)
```

The structlog processor chain (configured in `main.py`) adds timestamp, log level, and service name to every record automatically. Pipeline stage logs are distinguishable by the `pipeline_stage_complete` event name.

---

## Consequences

**Positive:**
- Removing the OpenAI embedding dependency from the pipeline eliminates per-token API costs for indexing and retrieval, making the pipeline cost-free to run at high volume.
- The 384-dim `all-MiniLM-L6-v2` vectors are 4× smaller than 1536-dim OpenAI vectors, reducing Qdrant memory and storage requirements by approximately 75% at equivalent collection size.
- The deterministic chunk point ID (UUID v5 from source_id + chunk_index) makes the Index stage idempotent: re-running the pipeline for a session overwrites existing points without creating duplicates.
- The `PipelineStageLog` TypedDict provides a machine-readable contract that CI can validate — any stage that fails to emit a compliant record causes a test failure rather than silent data loss.
- RAG context injection into the Planner reduces redundant research across sessions on the same topic, lowering both Tavily API call costs and total session latency.
- Graceful degradation on RAG miss (return `None`, skip context block) means Qdrant unavailability never causes a session to fail — it degrades to Milestone 1 behaviour.

**Negative / trade-offs:**
- `all-MiniLM-L6-v2` produces lower-quality embeddings than OpenAI `text-embedding-3-small` for long-form semantic search. This is an explicit quality trade-off for cost. The 0.45 score threshold was calibrated for MiniLM; it may need tuning as the collection grows.
- Loading the sentence-transformers model (~90 MB) at startup increases cold-start time by approximately 2–4 seconds on Railway's standard instances. The `ensure_embedder_loaded()` startup hook makes this predictable (paid once at startup, not on first request).
- Chunking multiplies Qdrant point count relative to source count: a 2,000-word source (~2,700 tokens) produces 6 chunks. 1,000 sources with mean 900 words yields approximately 2,500–3,000 Qdrant points. Collection size grows at 2.5–3× the source count.
- The MinHash LSH deduplication threshold (0.85 Jaccard) may over-drop sources on topics with high factual overlap (e.g. breaking news). This is preferable to under-dropping, but the threshold is a tunable parameter.
- The benchmark mocks Qdrant I/O. Real production indexing performance includes network latency to the Qdrant instance (Railway → Qdrant Cloud is typically 5–20 ms per batch). The 60-second target should be re-validated against a live Qdrant instance before the Milestone 2 production cut-over.

**Risks:**
- The RAG score threshold (0.45) is set without empirical calibration against the production dataset. If the threshold is too high, the Planner will rarely receive context (cold-start behaviour persists). If too low, irrelevant sources will pollute the plan. A/B testing of the threshold value is planned for post-Milestone-2 optimisation.
- `spaCy en_core_web_sm` entity extraction accuracy on market intelligence text (company names, product names, financial metrics) is lower than domain-specific NER models. Entity quality affects the `entity_types` payload index usefulness for filtered search. This is acceptable for Milestone 2; a fine-tuned model is a Milestone 3 consideration.
