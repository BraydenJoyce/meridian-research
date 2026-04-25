import re
from datetime import UTC, datetime

import duckdb
import polars as pl
import structlog

logger = structlog.get_logger(__name__)

HIGH_AUTHORITY_DOMAINS = frozenset(
    {
        "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "nytimes.com",
        "techcrunch.com", "forbes.com", "hbr.org", "mckinsey.com", "gartner.com",
        "statista.com", "sec.gov", "arxiv.org", "nature.com", "github.com",
        "crunchbase.com", "pitchbook.com",
    }
)
MED_AUTHORITY_DOMAINS = frozenset(
    {
        "medium.com", "substack.com", "linkedin.com", "venturebeat.com",
        "zdnet.com", "wired.com", "businessinsider.com",
    }
)

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

ENTITY_PATTERN = re.compile(
    r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b"
)


def _domain_score(domain: str | None) -> float:
    if not domain:
        return 0.2
    d = domain.removeprefix("www.")
    if d in HIGH_AUTHORITY_DOMAINS:
        return 1.0
    if d in MED_AUTHORITY_DOMAINS:
        return 0.6
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


def score(con: duckdb.DuckDBPyConnection) -> int:
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
            0.35 * _domain_score(row["domain"])
            + 0.25 * _length_score(row["raw_content"])
            + 0.25 * _entity_density(row["raw_content"])
            + 0.15 * _recency_score(row["fetched_at"]),
            4,
        )
        for row in df.iter_rows(named=True)
    ]
    df = df.with_columns(pl.Series("quality_score", quality_scores))

    existing = {
        r[0] for r in con.execute("SELECT id FROM scored_sources").fetchall()
    }
    insert_rows = [
        (
            row["id"], row["session_id"], row["url"], row["title"],
            row["domain"], row["sub_task_index"], row["raw_content"],
            row["fetched_at"], row["quality_score"],
        )
        for row in df.iter_rows(named=True)
        if row["id"] not in existing
    ]
    if insert_rows:
        con.executemany(
            "INSERT INTO scored_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            insert_rows,
        )

    records_out = int(con.execute("SELECT COUNT(*) FROM scored_sources").fetchone()[0])  # type: ignore[index]

    logger.info(
        "pipeline.score",
        stage_name="score",
        records_in=records_in,
        records_out=records_out,
        records_dropped=0,
        reason=None,
    )
    return records_out
