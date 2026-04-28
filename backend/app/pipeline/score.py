"""Source quality scorer for the Meridian Research ETL pipeline.

Scores each source on 6 factors, each returning a float in [0.0, 1.0].
Final score is a weighted sum normalized to [0.0, 1.0].

Factor weights:
    domain_score:      0.25  - Domain authority (whitelist-based)
    length_score:      0.20  - Content length (step-function thresholds)
    entity_density:    0.15  - Named entity density (proxy for information richness)
    recency_score:     0.15  - Age decay (newer = better)
    citation_score:    0.15  - Presence of citations/references
    source_type_score: 0.10  - Source category (regulatory > academic > wire > trade > user)

Thresholds:
    QUALITY_THRESHOLD = 0.30: sources below this score are dropped from scored_sources.
    Entity extraction only processes sources with quality_score >= 0.40.
"""

import re
import time
from datetime import UTC, datetime

import duckdb
import polars as pl
import structlog

logger = structlog.get_logger(__name__)

# ── Quality gate ──────────────────────────────────────────────────────────────
QUALITY_THRESHOLD = 0.30

# ── Factor weights (must sum to 1.0) ─────────────────────────────────────────
_W_DOMAIN = 0.25
_W_LENGTH = 0.20
_W_ENTITY = 0.15
_W_RECENCY = 0.15
_W_CITATION = 0.15
_W_SOURCE_TYPE = 0.10

# ── Domain authority lists ────────────────────────────────────────────────────
ACADEMIC_REGULATORY_DOMAINS = frozenset(
    {"sec.gov", "arxiv.org", "nature.com", "pubmed.ncbi.nlm.nih.gov", "scholar.google.com"}
)
WIRE_SERVICE_DOMAINS = frozenset(
    {"reuters.com", "bloomberg.com", "wsj.com", "ft.com", "apnews.com", "afp.com"}
)
TRADE_PRESS_DOMAINS = frozenset(
    {
        "nytimes.com", "techcrunch.com", "forbes.com", "hbr.org", "mckinsey.com",
        "gartner.com", "statista.com", "github.com", "crunchbase.com", "pitchbook.com",
        "venturebeat.com", "zdnet.com", "wired.com", "businessinsider.com",
    }
)
USER_CONTENT_DOMAINS = frozenset({"medium.com", "substack.com", "linkedin.com", "reddit.com"})

HIGH_AUTHORITY_DOMAINS = WIRE_SERVICE_DOMAINS | ACADEMIC_REGULATORY_DOMAINS
MED_AUTHORITY_DOMAINS = TRADE_PRESS_DOMAINS

# ── Citation patterns ─────────────────────────────────────────────────────────
_CITATION_BRACKET = re.compile(r"\[\d+\]")
_CITATION_YEAR = re.compile(r"\(\d{4}\)")
_CITATION_DOI = re.compile(r"\bdoi:", re.IGNORECASE)
_CITATION_URL = re.compile(r"https?://\S+")

# ── Entity density pattern ────────────────────────────────────────────────────
ENTITY_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b")

CREATE_SCORED = """
CREATE TABLE IF NOT EXISTS scored_sources (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    url         TEXT NOT NULL,
    title       TEXT,
    domain      TEXT,
    sub_task_index INTEGER,
    raw_content TEXT,
    fetched_at  TEXT,
    quality_score DOUBLE NOT NULL
)
"""


def _domain_score(domain: str | None) -> float:
    if not domain:
        return 0.2
    d = domain.removeprefix("www.")
    if d in HIGH_AUTHORITY_DOMAINS:
        return 1.0
    if d in MED_AUTHORITY_DOMAINS:
        return 0.6
    if d.endswith(".gov") or d.endswith(".edu"):
        return 1.0
    return 0.3


def _length_score(text: str | None) -> float:
    if not text:
        return 0.0
    words = len(text.split())
    if words >= 500:
        return 1.0
    if words >= 200:
        return 0.7
    if words >= 50:
        return 0.4
    return 0.1


def _entity_density(text: str | None) -> float:
    if not text:
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    entities = ENTITY_PATTERN.findall(text)
    return min(len(entities) / max(len(words), 1) * 5, 1.0)


def _recency_score(fetched_at: str | None) -> float:
    if not fetched_at:
        return 0.5
    try:
        ts = datetime.fromisoformat(fetched_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        age_days = (datetime.now(UTC) - ts).days
        if age_days <= 30:
            return 1.0
        if age_days <= 180:
            return 0.7
        if age_days <= 365:
            return 0.4
        return 0.2
    except ValueError:
        return 0.5


def _citation_score(text: str | None) -> float:
    if not text:
        return 0.0
    count = (
        len(_CITATION_BRACKET.findall(text))
        + len(_CITATION_YEAR.findall(text))
        + len(_CITATION_DOI.findall(text))
    )
    if count == 0:
        return 0.0
    if count <= 2:
        return 0.4
    if count <= 5:
        return 0.7
    return 1.0


def _source_type_score(domain: str | None) -> float:
    if not domain:
        return 0.4
    d = domain.removeprefix("www.")
    if d.endswith(".gov") or d.endswith(".edu"):
        return 1.0
    if d in ACADEMIC_REGULATORY_DOMAINS:
        return 1.0
    if d in WIRE_SERVICE_DOMAINS:
        return 0.9
    if d in TRADE_PRESS_DOMAINS:
        return 0.7
    if d in USER_CONTENT_DOMAINS:
        return 0.3
    return 0.4


def score(con: duckdb.DuckDBPyConnection, session_id: str = "") -> int:
    t0 = time.perf_counter()
    con.execute(CREATE_SCORED)

    rows = con.execute(
        "SELECT id, session_id, url, title, domain, sub_task_index, raw_content, fetched_at "
        "FROM deduped_sources"
    ).fetchall()
    records_in = len(rows)

    df = pl.DataFrame(
        {
            "id": [r[0] for r in rows],
            "session_id": [r[1] for r in rows],
            "url": [r[2] for r in rows],
            "title": [r[3] for r in rows],
            "domain": [r[4] for r in rows],
            "sub_task_index": [r[5] for r in rows],
            "raw_content": [r[6] for r in rows],
            "fetched_at": [r[7] for r in rows],
        }
    )

    quality_scores = [
        round(
            _W_DOMAIN * _domain_score(row["domain"])
            + _W_LENGTH * _length_score(row["raw_content"])
            + _W_ENTITY * _entity_density(row["raw_content"])
            + _W_RECENCY * _recency_score(row["fetched_at"])
            + _W_CITATION * _citation_score(row["raw_content"])
            + _W_SOURCE_TYPE * _source_type_score(row["domain"]),
            4,
        )
        for row in df.iter_rows(named=True)
    ]
    df = df.with_columns(pl.Series("quality_score", quality_scores))

    existing = {r[0] for r in con.execute("SELECT id FROM scored_sources").fetchall()}
    insert_rows = [
        (
            row["id"], row["session_id"], row["url"], row["title"],
            row["domain"], row["sub_task_index"], row["raw_content"],
            row["fetched_at"], row["quality_score"],
        )
        for row in df.iter_rows(named=True)
        if row["id"] not in existing and row["quality_score"] >= QUALITY_THRESHOLD
    ]
    dropped = records_in - len(
        [r for r in df.iter_rows(named=True) if r["quality_score"] >= QUALITY_THRESHOLD]
    )
    if insert_rows:
        con.executemany(
            "INSERT INTO scored_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            insert_rows,
        )

    records_out = int(con.execute("SELECT COUNT(*) FROM scored_sources").fetchone()[0])  # type: ignore[index]
    duration_ms = (time.perf_counter() - t0) * 1000

    logger.info(
        "pipeline_stage_complete",
        stage_name="score",
        session_id=session_id,
        records_in=records_in,
        records_out=records_out,
        records_dropped=dropped,
        drop_reason="below_quality_threshold" if dropped > 0 else None,
        duration_ms=duration_ms,
    )
    return records_out
