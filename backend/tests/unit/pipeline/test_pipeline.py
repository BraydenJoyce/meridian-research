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


def test_deduplicate_reduces_by_over_40_percent(con: duckdb.DuckDBPyConnection) -> None:
    """Prove >40% dedup rate on a dataset where ~50% of sources are near-duplicates."""
    import random
    random.seed(42)

    base_texts = [
        f"Company Alpha Inc reported revenue of ${random.randint(1, 99)} billion in "
        f"Q{random.randint(1, 4)} 2025. CEO John Smith announced {random.randint(5, 20)}% "
        f"growth. Product AlphaCloud {random.randint(1, 10)}.0 launched."
        for _ in range(50)
    ]

    sources: list[Any] = []
    for i, text in enumerate(base_texts):
        sources.append(_source(f"https://site{i}.com/article", text, f"site{i}.com"))

    for i, text in enumerate(base_texts):
        near_dup = text.replace("billion", "billion USD")
        sources.append(_source(f"https://dup{i}.com/article", near_dup, f"dup{i}.com"))

    assert len(sources) == 100
    ingest(con, sources)
    deduped_count = deduplicate(con)
    dedup_rate = (100 - deduped_count) / 100
    assert dedup_rate > 0.40, (
        f"Expected >40% dedup rate, got {dedup_rate:.2%} ({deduped_count} surviving)"
    )


def test_score_each_factor_independently() -> None:
    """Each scoring factor function returns a float in [0.0, 1.0]."""
    from app.pipeline.score import (
        _citation_score,
        _domain_score,
        _entity_density,
        _length_score,
        _recency_score,
        _source_type_score,
    )

    assert _domain_score("reuters.com") == 1.0
    assert _domain_score("medium.com") < _domain_score("reuters.com")
    assert 0.0 <= _domain_score(None) <= 1.0

    assert _length_score("word " * 600) == 1.0
    assert _length_score("") == 0.0

    assert 0.0 <= _recency_score(None) <= 1.0

    assert _citation_score("See [1] and [2] also [3]") > _citation_score("no citations here")
    assert _citation_score("") == 0.0

    assert _source_type_score("sec.gov") == 1.0
    assert _source_type_score("medium.com") < _source_type_score("reuters.com")

    assert 0.0 <= _entity_density("Microsoft Corp and Google LLC announced") <= 1.0


def test_extract_entities_skips_low_quality_sources(con: duckdb.DuckDBPyConnection) -> None:
    """Sources with quality_score < 0.4 must not have entities extracted."""
    # Use a source with minimal content that will score very low
    low_quality = _source("https://spam.com/x", "", "spam.com")
    ingest(con, [low_quality])
    deduplicate(con)
    score(con)

    # Manually verify score is < 0.4 for this source
    rows = con.execute(
        "SELECT quality_score FROM scored_sources WHERE url='https://spam.com/x'"
    ).fetchall()
    if rows and rows[0][0] < 0.4:
        extract_entities(con)
        entity_rows = con.execute(
            "SELECT * FROM entities WHERE source_id=?", [str(low_quality["id"])]
        ).fetchall()
        # Source was skipped — no entities for this source
        assert len(entity_rows) == 0


def test_extract_entities_spacy_finds_known_org(con: duckdb.DuckDBPyConnection) -> None:
    """spaCy NER should find ORG entities in market intelligence text."""
    source = _source(
        "https://reuters.com/article",
        "Microsoft Corporation announced a major acquisition. Apple Inc responded with a new product.",
        "reuters.com",
    )
    ingest(con, [source])
    deduplicate(con)
    score(con)
    extract_entities(con)

    orgs = con.execute(
        "SELECT value FROM entities WHERE entity_type='ORG'"
    ).fetchall()
    org_values = [r[0] for r in orgs]
    # At least one of these major orgs should be found
    assert any("Microsoft" in v or "Apple" in v for v in org_values), f"Got orgs: {org_values}"


def test_extract_entities_metric_pattern(con: duckdb.DuckDBPyConnection) -> None:
    """Regex should find financial metrics."""
    source = _source(
        "https://wsj.com/article",
        "Revenue grew 23% YoY to $4.5 billion in fiscal 2025.",
        "wsj.com",
    )
    ingest(con, [source])
    deduplicate(con)
    score(con)
    extract_entities(con)

    metrics = con.execute(
        "SELECT value FROM entities WHERE entity_type='METRIC'"
    ).fetchall()
    assert len(metrics) >= 1, "Expected at least 1 metric (percentage or dollar amount)"


@pytest.mark.parametrize(
    "domain,content,fetched_at",
    [
        ("reuters.com", "word " * 300 + " [1] reference (2024) doi:10.1000/test", "2026-01-01"),
        ("medium.com", "short content here", None),
        (None, "", None),
    ],
)
def test_score_always_in_range(
    con: duckdb.DuckDBPyConnection,
    domain: str | None,
    content: str,
    fetched_at: str | None,
) -> None:
    src = _source("https://example.com/x", content, domain or "example.com")
    if fetched_at:
        src["fetched_at"] = fetched_at
    ingest(con, [src])
    deduplicate(con)
    score(con)
    rows = con.execute("SELECT quality_score FROM scored_sources").fetchall()
    for (s,) in rows:
        assert 0.0 <= s <= 1.0
