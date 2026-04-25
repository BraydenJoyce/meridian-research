import uuid
from typing import Any

import duckdb
import pytest

from app.pipeline.deduplicate import deduplicate
from app.pipeline.extract_entities import extract_entities
from app.pipeline.ingest import ingest
from app.pipeline.orchestrator import run_pipeline
from app.pipeline.score import score

SESSION_ID = uuid.uuid4()


def _source(
    url: str,
    raw_content: str = "",
    domain: str | None = None,
    sub_task_index: int = 0,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "session_id": SESSION_ID,
        "url": url,
        "title": f"Title for {url}",
        "domain": domain or url.split("/")[2],
        "sub_task_index": sub_task_index,
        "raw_content": raw_content,
        "fetched_at": None,
    }


UNIQUE_CONTENT = [
    "Salesforce Inc reported record ARR of $35 billion in Q1 2026 earnings call.",
    "HubSpot Corp announced a new AI CRM product HubSpot AI Platform v3.0 Enterprise launch.",
    "Microsoft Corporation acquired several CRM Technologies startups worth $2 billion.",
    "Gartner analysis shows CRM market growing at 14.5% annually with 80% enterprise adoption.",
    "Zoho Systems released annual report showing 40 million users worldwide across all products.",
    "SAP Group announced SAP Cloud Enterprise Platform with integrated AI analytics features.",
    "Oracle Corporation CTO Larry Ellison stated new database Oracle Autonomous DB 21 release.",
]

DUP_CONTENT = UNIQUE_CONTENT[0]

SOURCES_10: list[dict[str, Any]] = [
    _source("https://reuters.com/article-1", UNIQUE_CONTENT[0], "reuters.com"),
    _source("https://bloomberg.com/article-2", UNIQUE_CONTENT[1], "bloomberg.com"),
    _source("https://techcrunch.com/article-3", UNIQUE_CONTENT[2], "techcrunch.com"),
    _source("https://gartner.com/article-4", UNIQUE_CONTENT[3], "gartner.com"),
    _source("https://forbes.com/article-5", UNIQUE_CONTENT[4], "forbes.com"),
    _source("https://wsj.com/article-6", UNIQUE_CONTENT[5], "wsj.com"),
    _source("https://ft.com/article-7", UNIQUE_CONTENT[6], "ft.com"),
    # 3 near-duplicates of article-1 (same content → Jaccard=1.0 > 0.8 threshold)
    _source("https://example.com/dup-1", DUP_CONTENT, "example.com"),
    _source("https://example2.com/dup-2", DUP_CONTENT, "example2.com"),
    _source("https://example3.com/dup-3", DUP_CONTENT, "example3.com"),
]


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def test_ingest_loads_all_sources(con: duckdb.DuckDBPyConnection) -> None:
    count = ingest(con, SOURCES_10)
    assert count == 10


def test_ingest_idempotent(con: duckdb.DuckDBPyConnection) -> None:
    ingest(con, SOURCES_10)
    count_second = ingest(con, SOURCES_10)
    assert count_second == 10


def test_deduplicate_removes_known_duplicates(con: duckdb.DuckDBPyConnection) -> None:
    ingest(con, SOURCES_10)
    deduped_count = deduplicate(con)
    # 3 near-dupes removed → 7 unique
    assert deduped_count == 7


def test_deduplicate_idempotent(con: duckdb.DuckDBPyConnection) -> None:
    ingest(con, SOURCES_10)
    count_first = deduplicate(con)
    count_second = deduplicate(con)
    assert count_first == count_second


def test_score_produces_valid_range(con: duckdb.DuckDBPyConnection) -> None:
    ingest(con, SOURCES_10)
    deduplicate(con)
    score(con)

    rows = con.execute("SELECT quality_score FROM scored_sources").fetchall()
    assert len(rows) == 7
    for (s,) in rows:
        assert 0.0 <= s <= 1.0


def test_score_idempotent(con: duckdb.DuckDBPyConnection) -> None:
    ingest(con, SOURCES_10)
    deduplicate(con)
    count_first = score(con)
    count_second = score(con)
    assert count_first == count_second


def test_extract_entities_finds_org(con: duckdb.DuckDBPyConnection) -> None:
    ingest(con, SOURCES_10)
    deduplicate(con)
    score(con)
    extract_entities(con)

    orgs = con.execute(
        "SELECT value FROM entities WHERE entity_type = 'ORG'"
    ).fetchall()
    assert len(orgs) >= 1


def test_extract_entities_idempotent(con: duckdb.DuckDBPyConnection) -> None:
    ingest(con, SOURCES_10)
    deduplicate(con)
    score(con)
    count_first = extract_entities(con)
    count_second = extract_entities(con)
    assert count_first == count_second


def test_pipeline_end_to_end() -> None:
    result = run_pipeline(SOURCES_10)
    con = result["connection"]
    try:
        assert result["ingested"] == 10
        assert result["deduped"] == 7
        assert result["scored"] == 7
        assert result["entity_count"] >= 1
    finally:
        con.close()


def test_pipeline_idempotent() -> None:
    result1 = run_pipeline(SOURCES_10)
    result1["connection"].close()

    result2 = run_pipeline(SOURCES_10)
    result2["connection"].close()

    assert result1["ingested"] == result2["ingested"]
    assert result1["deduped"] == result2["deduped"]
    assert result1["scored"] == result2["scored"]
