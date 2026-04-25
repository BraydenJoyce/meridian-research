import uuid
from typing import Any

import duckdb
import structlog

logger = structlog.get_logger(__name__)

CREATE_RAW_SOURCES = """
CREATE TABLE IF NOT EXISTS raw_sources (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    url         TEXT NOT NULL,
    title       TEXT,
    domain      TEXT,
    sub_task_index INTEGER,
    raw_content TEXT,
    fetched_at  TEXT
)
"""


def ingest(con: duckdb.DuckDBPyConnection, sources: list[dict[str, Any]]) -> int:
    con.execute(CREATE_RAW_SOURCES)

    records_in = len(sources)
    existing = {
        row[0]
        for row in con.execute("SELECT id FROM raw_sources").fetchall()
    }

    rows = [
        (
            str(s["id"]),
            str(s["session_id"]),
            s["url"],
            s.get("title"),
            s.get("domain"),
            s.get("sub_task_index"),
            s.get("raw_content"),
            s.get("fetched_at"),
        )
        for s in sources
        if str(s["id"]) not in existing
    ]

    if rows:
        con.executemany(
            "INSERT INTO raw_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    records_out = int(con.execute("SELECT COUNT(*) FROM raw_sources").fetchone()[0])  # type: ignore[index]
    records_dropped = records_in - len(rows)

    logger.info(
        "pipeline.ingest",
        stage_name="ingest",
        records_in=records_in,
        records_out=records_out,
        records_dropped=records_dropped,
        reason="duplicate_id" if records_dropped > 0 else None,
    )
    return records_out


def make_source_dicts(
    session_id: uuid.UUID,
    rows: list[tuple[str, str, str | None, str | None, int | None, str | None]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": uuid.uuid4(),
            "session_id": session_id,
            "url": url,
            "title": title,
            "domain": domain,
            "sub_task_index": sub_task_index,
            "raw_content": raw_content,
            "fetched_at": None,
        }
        for url, title, domain, sub_task_index, raw_content, _ in rows
    ]
