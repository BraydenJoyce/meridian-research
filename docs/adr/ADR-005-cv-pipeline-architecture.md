# ADR-005: CV Pipeline Architecture and Modal API Contract

## Status
Accepted

## Context

Milestone 3 adds a Computer Vision (CV) pipeline to Meridian Research. When the
WebSearchAgent retrieves sources, many of those sources are documents, research
reports, and news articles that contain charts, tables, and figures carrying data
unavailable in raw text. The CV pipeline extracts structured data from those visual
elements and feeds it into the WriterAgent so the final report incorporates chart
data with full citations.

The CV pipeline must operate as a peer agent to WebSearchAgent — running in parallel
with it, not after it — so that chart extraction does not extend the critical path.
The pipeline runner already executes a sequential chain (Planner → WebSearch → ETL
→ Writer). The CV agent runs concurrently with WebSearch inside that sequence (see
Integration section below).

GPU inference is mandatory for YOLOv8 in production. The Railway backend has no
GPU. Modal is the GPU inference host: it provides serverless, on-demand GPU
containers that spin up on request and are invoked over HTTP.

**Constraints inherited from prior ADRs:**
- All I/O in the backend is non-blocking async (ADR-001).
- All agents implement `ResearchAgent` ABC (ADR-003).
- All durable state goes into Supabase PostgreSQL (ADR-001).
- Backend → external services via `async httpx` (ADR-001 tech stack).
- `ANTHROPIC_API_KEY` is already required at startup (ADR-003). The CV pipeline
  reuses it for Claude Vision calls on the Modal server.
- The `agent_events.agent_type` CHECK constraint and `event_type` CHECK constraint
  in PostgreSQL (ADR-002) must be extended via Alembic migration to include the new
  values defined in this ADR.

---

## Decision

### 1. Agent Integration — Parallel Execution with WebSearch

The `CvDocumentAgent` runs concurrently with `WebSearchAgent` using
`asyncio.gather`. The pipeline runner coordinates both agents as a pair, collecting
both results before proceeding to ETL.

**Revised pipeline sequence:**

```
Planner → [WebSearch ‖ CvDocumentAgent] → ETL → Writer
```

The pipeline runner spawns both agents with `asyncio.gather` after the Planner
completes. Both agents receive the same Planner output as input. The runner waits
for both to finish before passing their merged outputs to the ETL agent.

**Pipeline runner change (backend/app/pipeline/runner.py):**

The existing `run_pipeline` function is updated to replace the direct
`WebSearchAgent.run()` call with:

```python
web_search_result, cv_result = await asyncio.gather(
    web_search_agent.run(context),
    cv_agent.run(context),
    return_exceptions=False,
)
context.update(web_search_result)
context.update(cv_result)
```

If `CvDocumentAgent.run()` raises `AgentError`, the pipeline runner logs a warning,
sets `cv_result = {"chart_results": [], "chart_count": 0}` (zero charts), and
continues. CV failure must never abort a session — text-only reports are acceptable.
If `CvDocumentAgent.run()` raises `AgentFatalError`, it is treated identically to
`AgentError` (degraded, not fatal). The session can always be completed without CV
data.

---

### 2. CvDocumentAgent Class Interface

**File:** `backend/app/agents/cv_document.py`

**agent_type value:** `"cv_document"`

**Class definition:**

```python
import uuid
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentError, AgentEvent, EventEmitter, ResearchAgent
from app.schemas.cv import ChartResult

logger = structlog.get_logger(__name__)


class CvDocumentAgent(ResearchAgent):
    """
    Extracts structured chart data from document images discovered during research.

    Runs concurrently with WebSearchAgent. Fetches images from source URLs already
    collected in the sources table (identified by session_id), classifies each
    document via Modal, and extracts chart data via Modal + Claude Vision.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        emitter: EventEmitter,
        db: AsyncSession,
        modal_base_url: str,
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db
        self._modal_base_url = modal_base_url.rstrip("/")
        self._http: httpx.AsyncClient | None = None

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Parameters
        ----------
        input_data : dict
            Must contain: session_id (uuid.UUID), question (str), sub_tasks (list[str]).
            Does NOT require source_ids — the agent queries the sources table directly
            using self.session_id.

        Returns
        -------
        dict with keys:
            chart_results : list[dict]
                Each dict is a serialised ChartResult (see Section 4).
                Empty list if no charts were found or extraction failed.
            chart_count : int
                Total number of ChartResult objects in chart_results.
        """
        ...
```

**Constructor parameters (all required, no defaults):**

| Parameter | Type | Source |
|---|---|---|
| `session_id` | `uuid.UUID` | Provided by pipeline runner (same as all agents) |
| `emitter` | `EventEmitter` | Provided by pipeline runner (same as all agents) |
| `db` | `AsyncSession` | Provided by pipeline runner (same pattern as WriterAgent) |
| `modal_base_url` | `str` | From environment variable `MODAL_BASE_URL` |

**Pipeline runner construction:**

```python
cv_agent = CvDocumentAgent(
    session_id=session.id,
    emitter=emitter,
    db=db,
    modal_base_url=settings.MODAL_BASE_URL,
)
```

**run() input contract:**

```python
{
    "session_id": uuid.UUID,
    "question": str,
    "sub_tasks": list[str],
}
```

Note: `source_ids` is NOT required in input. The agent independently queries
`sources` where `session_id = self.session_id` to get candidate URLs. This is
because WebSearch and CvDocumentAgent run concurrently; sources may still be
populating when CvDocumentAgent starts. The agent uses a fixed 10-second startup
wait (non-blocking: `await asyncio.sleep(10)`) before querying sources to allow
WebSearch to populate at least its first sub-task results.

**run() output contract:**

```python
{
    "chart_results": list[dict],   # serialised ChartResult objects (model_dump())
    "chart_count": int,            # len(chart_results)
}
```

**Events emitted (in order):**

| event_type | agent_type | payload keys | description |
|---|---|---|---|
| `agent_started` | `cv_document` | `{"agent": "cv_document"}` | Emitted before any source queries |
| `cv_document_started` | `cv_document` | `{"source_url": str, "image_url": str}` | Before classifying each image |
| `cv_document_classified` | `cv_document` | `{"source_url": str, "image_url": str, "doc_class": str, "confidence": float}` | After /classify returns |
| `cv_chart_extracted` | `cv_document` | `{"source_url": str, "image_url": str, "chart_type": str}` | After successful /extract-chart |
| `agent_completed` | `cv_document` | `{"agent": "cv_document", "images_processed": int, "charts_extracted": int}` | After all images processed |
| `agent_failed` | `cv_document` | `{"agent": "cv_document", "error": str}` | Before raising AgentError (never AgentFatalError) |

**Image discovery logic:**

1. Query `sources` table: `SELECT url FROM sources WHERE session_id = :session_id AND raw_content IS NOT NULL`.
2. For each source URL, extract image URLs from `raw_content` using a regex pattern matching `<img src="...">` and Markdown `![...](...)`  patterns. Extract only URLs ending in `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` (case-insensitive).
3. Deduplicate image URLs. Cap at 50 images per session (skip remainder after first 50, log a warning).
4. Process images concurrently with `asyncio.gather`, max concurrency 5 (use `asyncio.Semaphore(5)`).

**HTTP client lifecycle:**

The agent creates a single `httpx.AsyncClient` at the start of `run()` and closes
it at the end, using `async with httpx.AsyncClient(...) as self._http:`. Timeout:
30 seconds per request (`httpx.Timeout(30.0)`).

---

### 3. Modal Inference Server API Contract

**Deployment:** The Modal app is deployed at a stable URL assigned at deploy time.
The URL is stored in environment variable `MODAL_BASE_URL` on Railway.

**Base URL pattern:** `https://{modal-org}--meridian-cv-{env}.modal.run`

Example: `https://meridian-labs--meridian-cv-prod.modal.run`

The exact URL is determined at Modal deployment time and stored as `MODAL_BASE_URL`.
All backend → Modal calls are prefixed with `MODAL_BASE_URL`.

**Authentication:** All Modal endpoints require a bearer token. The token is stored
in environment variable `MODAL_API_SECRET` on Railway. Backend sets the HTTP header:

```
Authorization: Bearer {MODAL_API_SECRET}
```

Modal validates this token in a shared middleware function applied to both endpoints.
The token is a static secret (not a JWT) — set once at deployment, rotated manually.

**Modal app file:** `ml/inference/app.py`

---

#### Endpoint 1 — POST /classify

**Purpose:** Run the YOLOv8 ONNX document classifier on a single image URL.
Returns the document class and confidence score.

**Request:**

```json
{
  "image_url": "https://example.com/figure1.png",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `image_url` | `string` | Yes | Must be a valid HTTP/HTTPS URL. Max length 2048. |
| `session_id` | `string` | Yes | UUID v4 string. Used for structured logging on the Modal side. |

**Response (HTTP 200):**

```json
{
  "image_url": "https://example.com/figure1.png",
  "doc_class": "bar_chart",
  "confidence": 0.9423,
  "latency_ms": 48.2
}
```

| Field | Type | Always present | Description |
|---|---|---|---|
| `image_url` | `string` | Yes | Echo of the input image_url |
| `doc_class` | `string` | Yes | One of the 8 class strings listed below |
| `confidence` | `float` | Yes | Model confidence 0.0–1.0 |
| `latency_ms` | `float` | Yes | Inference wall-clock time in milliseconds |

**8 document classes (exhaustive — no other values will be returned):**

| `doc_class` value | Description |
|---|---|
| `bar_chart` | Bar or column chart |
| `line_chart` | Line chart or time-series graph |
| `pie_chart` | Pie or donut chart |
| `scatter_plot` | Scatter plot or bubble chart |
| `table` | Data table with rows and columns |
| `diagram` | Flowchart, org chart, or process diagram |
| `infographic` | Mixed visual with text callouts |
| `other` | Does not match any of the above classes |

**Error responses:**

| HTTP status | `error` value | Condition |
|---|---|---|
| `422` | `"invalid_image_url"` | URL is not a valid HTTP/HTTPS URL |
| `422` | `"image_fetch_failed"` | Modal server could not download the image |
| `422` | `"image_too_large"` | Image exceeds 10 MB |
| `500` | `"inference_error"` | ONNX runtime threw an exception |
| `401` | `"unauthorized"` | Missing or invalid Authorization header |

Error response body:
```json
{
  "error": "image_fetch_failed",
  "detail": "HTTP 403 from origin server"
}
```

**Backend routing logic:** After receiving `/classify` response, the backend
proceeds to `/extract-chart` only if `doc_class` is one of: `bar_chart`,
`line_chart`, `pie_chart`, `scatter_plot`, `table`. Classes `diagram`,
`infographic`, and `other` are skipped — no chart extraction is attempted.
The confidence threshold for proceeding is `confidence >= 0.70`. Images below this
threshold are skipped regardless of `doc_class`.

---

#### Endpoint 2 — POST /extract-chart

**Purpose:** Given an image URL that has already been classified as a chart,
use Claude Vision (claude-sonnet-4-6) to extract structured chart data.

**Request:**

```json
{
  "image_url": "https://example.com/figure1.png",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "source_url": "https://example.com/report.html",
  "doc_class": "bar_chart"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `image_url` | `string` | Yes | Must be a valid HTTP/HTTPS URL. Max length 2048. |
| `session_id` | `string` | Yes | UUID v4 string. |
| `source_url` | `string` | Yes | URL of the web page that contained this image. Used for citation. Max length 2048. |
| `doc_class` | `string` | Yes | Must be one of the 5 extractable classes: `bar_chart`, `line_chart`, `pie_chart`, `scatter_plot`, `table`. |

**Response (HTTP 200):**

```json
{
  "image_url": "https://example.com/figure1.png",
  "source_url": "https://example.com/report.html",
  "chart_type": "bar_chart",
  "title": "Global EV Sales by Region 2020–2024",
  "x_axis": "Year",
  "y_axis": "Units Sold (millions)",
  "series": [
    {
      "name": "North America",
      "data_points": [
        {"label": "2020", "value": 0.32},
        {"label": "2021", "value": 0.48},
        {"label": "2022", "value": 0.91},
        {"label": "2023", "value": 1.24},
        {"label": "2024", "value": 1.67}
      ]
    },
    {
      "name": "Europe",
      "data_points": [
        {"label": "2020", "value": 0.74},
        {"label": "2021", "value": 1.12},
        {"label": "2022", "value": 1.63},
        {"label": "2023", "value": 2.01},
        {"label": "2024", "value": 2.45}
      ]
    }
  ],
  "key_insight": "European EV sales have consistently outpaced North America by approximately 2x, with both regions showing accelerating growth post-2021.",
  "latency_ms": 2340.5
}
```

**Response field specification:**

| Field | Type | Nullable | Description |
|---|---|---|---|
| `image_url` | `string` | No | Echo of input image_url |
| `source_url` | `string` | No | Echo of input source_url |
| `chart_type` | `string` | No | One of the 5 extractable doc_class values |
| `title` | `string` | Yes (`null`) | Chart title if visible; `null` if no title present |
| `x_axis` | `string` | Yes (`null`) | X-axis label if present; `null` for pie charts and tables |
| `y_axis` | `string` | Yes (`null`) | Y-axis label if present; `null` for pie charts and tables |
| `series` | `array` | No | Array of SeriesItem objects (see below). Minimum 1 item. |
| `key_insight` | `string` | No | 1–2 sentence plain-English summary of the chart's most important finding. Always populated by Claude Vision. |
| `latency_ms` | `float` | No | Wall-clock time for Claude Vision call in milliseconds |

**SeriesItem object:**

```json
{
  "name": "string",
  "data_points": [
    {"label": "string", "value": "number | string"}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `series[].name` | `string` | Series name. For single-series charts: `"value"`. For pie charts: the slice label. |
| `series[].data_points` | `array` | Ordered list of data points |
| `series[].data_points[].label` | `string` | X-axis label or category name |
| `series[].data_points[].value` | `number \| string` | Numeric value if parseable; raw string otherwise |

For `table` doc_class: `series` contains one SeriesItem per column. `series[].name`
is the column header. `series[].data_points` contains one entry per row, where
`label` is the row header (first column value) and `value` is the cell value.

**Error responses:**

| HTTP status | `error` value | Condition |
|---|---|---|
| `422` | `"invalid_image_url"` | URL is not valid |
| `422` | `"image_fetch_failed"` | Could not download image |
| `422` | `"unsupported_doc_class"` | doc_class is not in the 5 extractable classes |
| `422` | `"extraction_failed"` | Claude Vision returned unparseable output after 2 retries |
| `500` | `"claude_api_error"` | Anthropic API returned an error |
| `401` | `"unauthorized"` | Missing or invalid Authorization header |

---

### 4. ChartResult Pydantic Schema

**File:** `backend/app/schemas/cv.py`

This schema is the canonical Python representation of a successfully extracted chart.
It is the output type of `CvDocumentAgent` and the input type consumed by the
WriterAgent prompt builder.

```python
from __future__ import annotations
from typing import Union
from pydantic import BaseModel, Field, HttpUrl


class DataPoint(BaseModel):
    """A single x→y data point within a chart series."""
    label: str = Field(..., description="Category label or x-axis tick value")
    value: Union[float, str] = Field(
        ...,
        description="Numeric value if parseable; raw string from chart otherwise",
    )


class SeriesItem(BaseModel):
    """One data series within a chart (one line, one bar group, one pie slice set)."""
    name: str = Field(..., description="Series name. 'value' for single-series charts.")
    data_points: list[DataPoint] = Field(
        ...,
        min_length=1,
        description="Ordered list of data points for this series.",
    )


class ChartResult(BaseModel):
    """
    Structured data extracted from a single chart image.
    Produced by CvDocumentAgent; consumed by WriterAgent.
    Stored in chart_extractions table (one row per ChartResult).
    """
    image_url: str = Field(..., description="URL of the source image")
    source_url: str = Field(..., description="URL of the web page containing the image")
    chart_type: str = Field(
        ...,
        description=(
            "One of: bar_chart, line_chart, pie_chart, scatter_plot, table"
        ),
    )
    title: str | None = Field(
        None,
        description="Chart title as it appears in the image; None if not present",
    )
    x_axis: str | None = Field(
        None,
        description="X-axis label; None for pie charts and tables",
    )
    y_axis: str | None = Field(
        None,
        description="Y-axis label; None for pie charts and tables",
    )
    series: list[SeriesItem] = Field(
        ...,
        min_length=1,
        description="All data series extracted from the chart",
    )
    key_insight: str = Field(
        ...,
        description=(
            "1–2 sentence plain-English summary of the chart's key finding. "
            "Always populated — never empty string."
        ),
    )
```

**Validation rules enforced by Pydantic:**
- `chart_type` must be one of: `bar_chart`, `line_chart`, `pie_chart`,
  `scatter_plot`, `table`. Add a `field_validator` using:
  ```python
  @field_validator("chart_type")
  @classmethod
  def validate_chart_type(cls, v: str) -> str:
      allowed = {"bar_chart", "line_chart", "pie_chart", "scatter_plot", "table"}
      if v not in allowed:
          raise ValueError(f"chart_type must be one of {allowed}, got {v!r}")
      return v
  ```
- `series` must have at least 1 item (`min_length=1`).
- `key_insight` must be non-empty string; enforce with:
  ```python
  @field_validator("key_insight")
  @classmethod
  def validate_key_insight(cls, v: str) -> str:
      if not v.strip():
          raise ValueError("key_insight must not be empty")
      return v.strip()
  ```

---

### 5. Chart Data Storage — Separate `chart_extractions` Table

**Decision:** Chart extraction results are stored in a dedicated
`chart_extractions` table, not as a new column on `research_sessions`.

**Justification:**
- A session produces 0–50 `ChartResult` objects. Storing them in a JSONB array on
  `research_sessions` would create unbounded row bloat on a frequently-queried table.
- Each `ChartResult` is independently addressable (can be paginated, filtered by
  chart_type, linked back to a `source_url`). Separate rows enable this without
  deserialising the entire JSONB array.
- The `sources` table already establishes the pattern of one-row-per-artifact.
  `chart_extractions` follows the same pattern for CV artifacts.
- Future milestones may add user-facing chart browsing (e.g. "show me all charts
  from this report"). A separate table is required for that feature with acceptable
  query performance.

**SQL DDL (add to Alembic migration for Milestone 3):**

```sql
CREATE TABLE chart_extractions (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID            NOT NULL REFERENCES research_sessions (id) ON DELETE CASCADE,
    image_url           TEXT            NOT NULL,
    source_url          TEXT            NOT NULL,
    chart_type          TEXT            NOT NULL
                                            CHECK (chart_type IN (
                                                'bar_chart', 'line_chart', 'pie_chart',
                                                'scatter_plot', 'table'
                                            )),
    title               TEXT            NULL,
    x_axis              TEXT            NULL,
    y_axis              TEXT            NULL,
    series              JSONB           NOT NULL DEFAULT '[]',
    key_insight         TEXT            NOT NULL,
    doc_class_confidence NUMERIC(5, 4)  NULL
                                            CHECK (doc_class_confidence IS NULL
                                                   OR doc_class_confidence BETWEEN 0 AND 1),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chart_extractions_session_id
    ON chart_extractions (session_id);

CREATE INDEX idx_chart_extractions_chart_type
    ON chart_extractions (session_id, chart_type);
```

Note: `chart_extractions` does not have an `updated_at` column — rows are
write-once. No update trigger is needed.

**SQLAlchemy ORM model (backend/app/models/chart_extraction.py):**

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from app.models.base import Base


class ChartExtraction(MappedAsDataclass, Base):
    __tablename__ = "chart_extractions"
    __table_args__ = (
        CheckConstraint(
            "chart_type IN ('bar_chart','line_chart','pie_chart','scatter_plot','table')",
            name="ck_chart_extractions_chart_type",
        ),
        CheckConstraint(
            "doc_class_confidence IS NULL OR doc_class_confidence BETWEEN 0 AND 1",
            name="ck_chart_extractions_confidence",
        ),
    )

    # Required fields
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    chart_type: Mapped[str] = mapped_column(Text, nullable=False)
    key_insight: Mapped[str] = mapped_column(Text, nullable=False)
    series: Mapped[Any] = mapped_column(JSONB, nullable=False, default_factory=list)

    # Fields with defaults
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default_factory=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    x_axis: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    y_axis: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    doc_class_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, default=None
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=None,
        init=False,
    )
```

**Persistence in CvDocumentAgent:** After the `/extract-chart` call succeeds and
`ChartResult` is validated, the agent INSERTs one `ChartExtraction` row to
PostgreSQL via the injected `AsyncSession`. The INSERT happens immediately after
each successful extraction (not batched at the end) so that partial results are
durable if the agent is interrupted.

---

### 6. YOLOv8 Document Classifier — ONNX Serving Design

**Model file location (in repository):** `ml/models/doc_classifier.onnx`

**Training:** The YOLOv8 classification model is trained using `ultralytics` on a
labeled dataset of document images (8 classes). Training is run offline; only the
exported ONNX file is committed to the repository. Training scripts live in
`ml/train/`.

**ONNX export command (run after training, not at serve time):**

```bash
yolo export model=ml/models/doc_classifier.pt format=onnx opset=17 imgsz=224
```

The exported file is `ml/models/doc_classifier.onnx`. This file is committed to
git with Git LFS tracking (see Section 8 — .gitignore patterns).

**ONNX inference path on Modal server (ml/inference/app.py):**

```python
import onnxruntime as ort
import numpy as np
from PIL import Image
import httpx

# Loaded once at Modal container startup (not per-request)
_session: ort.InferenceSession | None = None

def get_ort_session() -> ort.InferenceSession:
    global _session
    if _session is None:
        _session = ort.InferenceSession(
            "/models/doc_classifier.onnx",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
    return _session


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """
    Resize to 224×224, convert to float32 RGB, normalise to [0, 1],
    apply ImageNet mean/std, return shape (1, 3, 224, 224) NCHW array.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((224, 224), Image.LANCZOS)
    arr = np.array(img, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    arr = arr.transpose(2, 0, 1)          # HWC → CHW
    return arr[np.newaxis, ...]           # add batch dim → (1, 3, 224, 224)


CLASS_NAMES = [
    "bar_chart", "line_chart", "pie_chart", "scatter_plot",
    "table", "diagram", "infographic", "other",
]

def run_classifier(image_bytes: bytes) -> tuple[str, float]:
    """Returns (doc_class, confidence)."""
    session = get_ort_session()
    input_array = preprocess_image(image_bytes)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: input_array})
    logits = outputs[0][0]               # shape: (8,)
    probs = softmax(logits)
    class_idx = int(np.argmax(probs))
    return CLASS_NAMES[class_idx], float(probs[class_idx])


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()
```

**ONNX inference path for running classifier outside Modal (local dev / CI):**

For local development and CI without GPU, the ONNX runtime falls back to
`CPUExecutionProvider` automatically (it is the second entry in the `providers`
list above). No code change is required. Set environment variable
`ONNXRUNTIME_PROVIDERS=CPUExecutionProvider` to force CPU-only and suppress the
CUDA warning log.

To run the classifier locally without Modal:

```python
# backend/app/services/cv_local.py  — used only in tests and local dev
import onnxruntime as ort
from app.schemas.cv import ChartResult

async def classify_local(image_url: str) -> tuple[str, float]:
    """Direct ONNX inference, bypassing Modal. For tests and local dev only."""
    image_bytes = await _fetch_image(image_url)
    return run_classifier(image_bytes)
```

When `MODAL_BASE_URL` environment variable is absent or set to `"local"`, the
`CvDocumentAgent` uses `cv_local.classify_local()` instead of the Modal
`/classify` endpoint. This enables full integration tests without a Modal
deployment.

---

### 7. Claude Vision Integration on Modal (Chart Extractor Design)

**Model:** `claude-sonnet-4-6` (NOT `claude-3-5-sonnet-20241022`).

**Location:** The Claude Vision call is made on the Modal server, inside the
`/extract-chart` endpoint handler. The Modal server holds the `ANTHROPIC_API_KEY`
as a Modal Secret named `meridian-anthropic-secret`.

**Prompt template (exact, used verbatim in ml/inference/app.py):**

```
You are a data extraction assistant. You will be given an image of a {doc_class}.
Extract all data visible in the chart into structured JSON.

Respond with ONLY a JSON object matching this exact schema — no markdown, no
explanation, no code fences:

{{
  "title": "<chart title or null>",
  "x_axis": "<x-axis label or null>",
  "y_axis": "<y-axis label or null>",
  "series": [
    {{
      "name": "<series name>",
      "data_points": [
        {{"label": "<x value or category>", "value": <numeric value or "string">}}
      ]
    }}
  ],
  "key_insight": "<1-2 sentence summary of the most important finding in this chart>"
}}

Rules:
- For pie charts: x_axis and y_axis must be null. Each slice is one DataPoint where
  label is the slice name and value is the percentage (as a float, e.g. 34.5).
- For tables: x_axis and y_axis must be null. Each column is one series. series[].name
  is the column header. data_points[].label is the row header. data_points[].value
  is the cell value.
- If a numeric value is not readable, use the string "unreadable" as the value.
- key_insight must always be populated. Never leave it empty or null.
- Output ONLY the JSON object. No other text.
```

**Retry logic:** If Claude Vision returns output that fails JSON parsing or Pydantic
validation, retry once with the same prompt appended with: `"\n\nYour previous
response was not valid JSON. Respond with ONLY the JSON object."`. After 2 failures,
return HTTP 422 with `error: "extraction_failed"`.

**Image delivery to Claude Vision:** Download the image on the Modal server (same
`httpx` fetch used for ONNX preprocessing). Pass the image bytes as a base64-encoded
`image` block in the Anthropic messages API:

```python
import base64

image_b64 = base64.standard_b64encode(image_bytes).decode()
message = await client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2048,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",   # set correctly per actual content-type
                    "data": image_b64,
                },
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
    }],
)
```

---

### 8. WriterAgent Prompt Modification — Chart Data Injection

**File modified:** `backend/app/agents/writer.py`

**Injection point:** The chart data block is injected into the user message, between
the `<sources>` block and the final instruction line `"Research question: ..."`.

**Exact user message structure after injection:**

```python
messages=[
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": sources_block,           # existing <sources>...</sources> XML
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": chart_data_block,         # NEW: inserted here, only if charts exist
            },
            {
                "type": "text",
                "text": (
                    f"Research question: {question}\n\n"
                    "Write the full markdown intelligence report now."
                ),
            },
        ],
    }
]
```

The `chart_data_block` text is omitted entirely (the list item is not added) when
`chart_results` is empty or absent in the pipeline context. The WriterAgent reads
`input_data.get("chart_results", [])` and only builds and injects the block if the
list is non-empty.

**`chart_data_block` format (exact):**

```python
def _format_chart_data_block(chart_results: list[dict]) -> str:
    """
    Format chart data for injection into the WriterAgent prompt.
    chart_results is a list of ChartResult.model_dump() dicts.
    """
    lines = ["## Data from Charts\n"]
    lines.append(
        "The following structured data was extracted from charts and figures "
        "found in the research sources. Incorporate relevant chart data into "
        "your analysis sections. Cite the source_url for each chart used.\n"
    )
    for i, chart in enumerate(chart_results, 1):
        lines.append(f"### Chart {i}: {chart.get('title') or 'Untitled'}")
        lines.append(f"- **Type:** {chart['chart_type']}")
        lines.append(f"- **Source:** {chart['source_url']}")
        if chart.get("x_axis"):
            lines.append(f"- **X-axis:** {chart['x_axis']}")
        if chart.get("y_axis"):
            lines.append(f"- **Y-axis:** {chart['y_axis']}")
        lines.append(f"- **Key insight:** {chart['key_insight']}")
        lines.append("- **Data:**")
        for series in chart.get("series", []):
            lines.append(f"  - Series: {series['name']}")
            for dp in series.get("data_points", []):
                lines.append(f"    - {dp['label']}: {dp['value']}")
        lines.append("")
    return "\n".join(lines)
```

**WriterAgent system prompt addition:** Append the following sentence to
`SYSTEM_PROMPT` in `writer.py`:

```
"- When chart data is provided in the '## Data from Charts' section, reference "
"specific data points from charts in your analysis and cite the chart's source_url "
"using the standard inline citation format [Source Title](url).\n"
```

This sentence is appended after the existing `"- Minimum 3 citations across the report"` line.

---

### 9. agent_events Schema Extensions

The `agent_events.agent_type` and `agent_events.event_type` CHECK constraints
(defined in ADR-002) must be extended via an Alembic migration for Milestone 3.

**New `agent_type` values to add:**

```sql
-- In migration: extend the CHECK constraint to include 'cv_document'
-- Note: PostgreSQL does not allow ALTER CONSTRAINT; drop and recreate the CHECK.
ALTER TABLE agent_events
    DROP CONSTRAINT IF EXISTS agent_events_agent_type_check;
ALTER TABLE agent_events
    ADD CONSTRAINT agent_events_agent_type_check
    CHECK (agent_type IN ('planner', 'web_search', 'etl', 'writer', 'system', 'cv_document'));
```

**New `event_type` values to add:**

```sql
ALTER TABLE agent_events
    DROP CONSTRAINT IF EXISTS agent_events_event_type_check;
ALTER TABLE agent_events
    ADD CONSTRAINT agent_events_event_type_check
    CHECK (event_type IN (
        'agent_started', 'agent_completed', 'agent_failed',
        'sub_task_started', 'sub_task_completed',
        'source_fetched', 'etl_progress', 'report_chunk', 'done', 'error',
        'cv_document_started', 'cv_document_classified', 'cv_chart_extracted'
    ));
```

Both constraint changes are included in the same Alembic migration that creates
the `chart_extractions` table.

---

### 10. Environment Variables

All environment variables are required at backend startup unless marked optional.
The application must fail to start if required variables are absent.

| Variable | Required | Description |
|---|---|---|
| `MODAL_BASE_URL` | Yes | Base URL of the Modal inference server, e.g. `https://meridian-labs--meridian-cv-prod.modal.run` |
| `MODAL_API_SECRET` | Yes | Bearer token for Modal endpoint authentication |
| `ANTHROPIC_API_KEY` | Already required (ADR-003) | Reused by Modal server for Claude Vision calls (passed as Modal Secret, not re-transmitted from Railway) |

`MODAL_API_SECRET` is stored as a Railway environment variable on the backend and
as a Modal Secret named `meridian-backend-secret` on the Modal side. The Modal
`/classify` and `/extract-chart` handlers verify `Authorization: Bearer {MODAL_API_SECRET}`.

**Local dev override:** Set `MODAL_BASE_URL=local` to bypass Modal entirely and use
the local ONNX path (`cv_local.py`). The `CvDocumentAgent` checks for this sentinel
value at construction time.

---

### 8. .gitignore Patterns for ml/models/ Artifacts

The following patterns are added to `ml/.gitignore` (create this file if it does
not exist):

```gitignore
# YOLOv8 training runs (large directories, not committed)
runs/
train/runs/

# PyTorch checkpoint files — committed only as .onnx via Git LFS
*.pt
*.pth
*.ckpt

# ONNX model files — tracked via Git LFS, not as regular git objects
# Add these to .gitattributes: *.onnx filter=lfs diff=lfs merge=lfs -text
# Do NOT add *.onnx to .gitignore — they must be tracked by Git LFS.

# Ultralytics cache and dataset artifacts
datasets/
.cache/
*.cache

# ONNX runtime profiling output
*.json.prof

# Weights & Biases artifacts
wandb/

# Python bytecode
__pycache__/
*.pyc
```

**Git LFS tracking (`.gitattributes` in repository root):**

```
ml/models/*.onnx filter=lfs diff=lfs merge=lfs -text
ml/models/*.pt filter=lfs diff=lfs merge=lfs -text
```

`doc_classifier.onnx` is tracked by Git LFS. It is NOT in `.gitignore`.
`doc_classifier.pt` (the PyTorch checkpoint before ONNX export) is tracked by Git
LFS if retained; it may also be excluded entirely by adding `*.pt` to
`ml/.gitignore` if the training team keeps the checkpoint externally.

---

## Implementation Notes

### File layout (additions for Milestone 3)

```
meridian-research/
├── backend/app/
│   ├── agents/
│   │   └── cv_document.py          # CvDocumentAgent implementation
│   ├── models/
│   │   └── chart_extraction.py     # ChartExtraction ORM model
│   ├── schemas/
│   │   └── cv.py                   # ChartResult, SeriesItem, DataPoint Pydantic models
│   └── pipeline/
│       └── runner.py               # Modified: asyncio.gather for Web+CV parallel spawn
├── ml/
│   ├── inference/
│   │   └── app.py                  # Modal app: /classify + /extract-chart endpoints
│   ├── models/
│   │   └── doc_classifier.onnx     # Git LFS tracked
│   ├── train/
│   │   └── train_classifier.py     # YOLOv8 training script (offline use)
│   └── .gitignore
├── backend/alembic/versions/
│   └── 0003_cv_pipeline.py         # chart_extractions table + agent_events constraint updates
└── backend/tests/
    └── test_cv_document_agent.py   # Unit tests for CvDocumentAgent
```

### Sequence diagram (one session, happy path)

```
User POST /api/research/create
  → worker dequeues session
  → PlannerAgent.run()              → sub_tasks
  → asyncio.gather(
      WebSearchAgent.run(),         → source_ids, source_count
      CvDocumentAgent.run()         → chart_results, chart_count
    )
  → ETL pipeline (orchestrator.py)
  → WriterAgent.run()               → report_markdown  [includes chart data block]
  → session status = completed
```

### CvDocumentAgent error handling summary

| Failure scenario | Behaviour |
|---|---|
| `MODAL_BASE_URL` env var absent at startup | Application fails to start (same as other required env vars) |
| Modal server returns HTTP 5xx | Log warning; skip that image; continue with others |
| Modal server returns HTTP 422 (`image_fetch_failed`) | Log warning; skip that image; continue |
| Modal server returns HTTP 401 | Raise `AgentError` immediately — all images will fail; pipeline continues with zero charts |
| All images return confidence < 0.70 | Return `{"chart_results": [], "chart_count": 0}` normally — not an error |
| `asyncio.gather` timeout (>120s total) | Raise `AgentError`; pipeline runner catches and continues with zero charts |
| No sources found in DB after 10s wait | Return `{"chart_results": [], "chart_count": 0}` normally — not an error |

### Unit testing CvDocumentAgent

Mock `httpx.AsyncClient` using `respx` (the async httpx mock library). Do not make
real HTTP calls in unit tests. Example:

```python
import respx
import pytest
from httpx import Response
from app.agents.cv_document import CvDocumentAgent

@pytest.mark.asyncio
async def test_classify_and_extract(fake_emitter, fake_db):
    with respx.mock:
        respx.post("https://modal.test/classify").mock(
            return_value=Response(200, json={
                "image_url": "https://example.com/chart.png",
                "doc_class": "bar_chart",
                "confidence": 0.95,
                "latency_ms": 42.0,
            })
        )
        respx.post("https://modal.test/extract-chart").mock(
            return_value=Response(200, json={...})  # full ChartResult JSON
        )
        agent = CvDocumentAgent(
            session_id=uuid.uuid4(),
            emitter=fake_emitter,
            db=fake_db,
            modal_base_url="https://modal.test",
        )
        result = await agent.run({"question": "test", "sub_tasks": ["q1"]})
        assert result["chart_count"] >= 0
```

### WriterAgent — pipeline context key consumed

The WriterAgent reads `input_data.get("chart_results", [])`. If the key is absent
(e.g. because CV agent was not run in an older session), the behaviour is identical
to an empty list — no chart block is injected. This ensures backward compatibility
with sessions created before Milestone 3.

---

## Consequences

**Positive:**
- Running `CvDocumentAgent` concurrently with `WebSearchAgent` adds zero latency
  to the critical path in sessions where web search is the bottleneck (which is
  the common case at 30–120 seconds).
- The `chart_extractions` table provides a clean, queryable record of all extracted
  chart data per session, enabling future features (chart browsing, data export).
- The Modal serverless GPU architecture means zero GPU cost when no sessions are
  running; costs scale linearly with usage.
- The ONNX classifier filter (run before Claude Vision) eliminates Claude Vision
  API calls for non-chart images, keeping CV pipeline costs proportional to actual
  chart density in the source set.
- Graceful degradation at every failure point (Modal down → zero charts → report
  still completes) means the CV pipeline never degrades the core product reliability.
- The `MODAL_BASE_URL=local` sentinel enables full local development and CI testing
  without a Modal deployment or GPU hardware.

**Negative / trade-offs:**
- The 10-second startup wait in `CvDocumentAgent` is a heuristic, not a guarantee.
  If WebSearch takes longer than 10 seconds to produce the first source (possible
  for large sub-task counts), the CV agent will find zero sources and return
  immediately with zero charts. A Milestone 4 improvement would be a proper
  event-driven trigger (e.g. subscribe to a Redis channel and process images as
  source URLs arrive).
- The Modal cold-start latency (GPU container spin-up: 5–20 seconds) means the
  first `/classify` call in a session may be slow. Subsequent calls within the
  same session reuse the warm container. Modal's `keep_warm=1` setting can
  eliminate cold starts but adds a fixed monthly cost.
- ONNX classifier accuracy depends on training data quality and diversity. Milestone
  3 ships with a baseline model; retraining is expected after production data is
  collected.
- Passing images to Claude Vision as base64 increases the Anthropic API token
  consumption by the image size. A 224×224 PNG is approximately 50 KB and counts
  as ~1,700 input tokens. At 50 images per session and $3/MTok (Sonnet pricing),
  chart extraction adds approximately $0.26 in API costs per session in the worst
  case (all 50 images are charts).

**Risks:**
- The `asyncio.gather` parallelism between WebSearch and CV depends on both agents
  being well-behaved async coroutines. Any blocking synchronous call inside either
  agent (e.g. a synchronous `requests.get`) will stall both agents. Code review
  must enforce `await` on all I/O in both agents.
- The Modal API secret (`MODAL_API_SECRET`) is a shared static token. If it is
  leaked, all Modal endpoints are accessible without rate limiting. Rotate
  immediately if leaked; implement per-session JWT tokens as a Milestone 4
  hardening task.
- The image regex extraction from `raw_content` is fragile — it depends on the
  WebSearch scraper preserving `<img>` tags and Markdown image syntax. If the ETL
  pipeline strips these tags during content cleaning (which `cleaned_content` likely
  does), the CV agent must query `raw_content`, not `cleaned_content`. This is
  already specified above but must be verified during implementation.
- `doc_class_confidence` threshold of 0.70 is set without empirical calibration.
  If the threshold is too high, few images will reach chart extraction. If too low,
  Claude Vision will process non-chart images and produce nonsense extractions.
  Threshold should be tunable via environment variable
  `CV_CONFIDENCE_THRESHOLD` (float, default `0.70`) to enable rapid adjustment
  without a code deploy.
