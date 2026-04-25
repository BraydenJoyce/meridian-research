import re

import duckdb
import structlog
from datasketch import MinHash, MinHashLSH

logger = structlog.get_logger(__name__)

NUM_PERM = 128
JACCARD_THRESHOLD = 0.8

CREATE_DEDUPED = """
CREATE TABLE IF NOT EXISTS deduped_sources (
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


def _shingles(text: str, k: int = 5) -> set[str]:
    text = re.sub(r"\s+", " ", text.lower().strip())
    if len(text) < k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def _make_minhash(text: str) -> MinHash:
    m = MinHash(num_perm=NUM_PERM)
    for s in _shingles(text):
        m.update(s.encode("utf-8"))
    return m


def deduplicate(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(CREATE_DEDUPED)

    rows = con.execute(
        "SELECT id, session_id, url, title, domain, sub_task_index, raw_content, fetched_at "
        "FROM raw_sources"
    ).fetchall()
    records_in = len(rows)

    lsh = MinHashLSH(threshold=JACCARD_THRESHOLD, num_perm=NUM_PERM)
    keep: list[tuple[str, ...]] = []
    dropped = 0

    for row in rows:
        rid, _session, _url, _title, _domain, _idx, raw_content, _fetched = row
        content = raw_content or _url
        mh = _make_minhash(content)

        candidates = lsh.query(mh)
        if candidates:
            dropped += 1
            continue

        lsh.insert(rid, mh)
        keep.append(row)

    existing = {
        r[0] for r in con.execute("SELECT id FROM deduped_sources").fetchall()
    }
    new_rows = [r for r in keep if r[0] not in existing]
    if new_rows:
        con.executemany("INSERT INTO deduped_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)", new_rows)

    records_out = int(con.execute("SELECT COUNT(*) FROM deduped_sources").fetchone()[0])  # type: ignore[index]

    logger.info(
        "pipeline.deduplicate",
        stage_name="deduplicate",
        records_in=records_in,
        records_out=records_out,
        records_dropped=dropped,
        reason="near_duplicate_minhash" if dropped > 0 else None,
    )
    return records_out
