"""Tests that all pipeline stages emit pipeline_stage_complete structured logs."""

import uuid

import duckdb
import structlog.testing

from app.pipeline.deduplicate import deduplicate
from app.pipeline.ingest import ingest
from app.pipeline.score import score

REQUIRED_KEYS = {
    "stage_name",
    "session_id",
    "records_in",
    "records_out",
    "records_dropped",
    "drop_reason",
    "duration_ms",
}

LONG_CONTENT = (
    "Salesforce Inc reported record ARR of $35 billion in Q1 2026 earnings call. "
    "HubSpot Corp announced a new AI CRM product HubSpot AI Platform v3.0 Enterprise. "
    "Microsoft Corporation acquired several CRM Technologies startups worth $2 billion. "
    "Gartner analysis shows CRM market growing at 14.5% annually with 80% enterprise adoption. "
    "Zoho Systems released annual report showing 40 million users worldwide across all products. "
)


def _sources(n: int) -> list[dict]:
    session_id = str(uuid.uuid4())
    return [
        {
            "id": uuid.uuid4(),
            "session_id": session_id,
            "url": f"https://reuters.com/article-{i}",
            "title": f"Article {i}",
            "domain": "reuters.com",
            "sub_task_index": i,
            "raw_content": LONG_CONTENT * 3,
            "fetched_at": "2026-01-01",
        }
        for i in range(n)
    ]


def test_all_stages_emit_structured_logs() -> None:
    con = duckdb.connect()
    session_id = str(uuid.uuid4())
    sources = _sources(5)
    # Stamp the session_id we control onto all sources so the log matches
    for s in sources:
        s["session_id"] = session_id

    with structlog.testing.capture_logs() as logs:
        ingest(con, sources, session_id=session_id)
        deduplicate(con, session_id=session_id)
        score(con, session_id=session_id)

    stage_logs = [lg for lg in logs if lg.get("event") == "pipeline_stage_complete"]
    assert len(stage_logs) >= 3, (
        f"Expected at least 3 pipeline_stage_complete events, got {len(stage_logs)}: "
        f"{[lg.get('stage_name') for lg in stage_logs]}"
    )

    for lg in stage_logs:
        missing = REQUIRED_KEYS - set(lg.keys())
        assert not missing, f"Stage log for '{lg.get('stage_name')}' missing keys: {missing}"


def test_ingest_stage_log_event_name() -> None:
    con = duckdb.connect()
    session_id = str(uuid.uuid4())
    sources = _sources(3)
    for s in sources:
        s["session_id"] = session_id

    with structlog.testing.capture_logs() as logs:
        ingest(con, sources, session_id=session_id)

    ingest_logs = [lg for lg in logs if lg.get("stage_name") == "ingest"]
    assert len(ingest_logs) == 1
    assert ingest_logs[0]["event"] == "pipeline_stage_complete"
    assert ingest_logs[0]["session_id"] == session_id
    assert ingest_logs[0]["records_in"] == 3
    assert ingest_logs[0]["records_out"] == 3
    assert ingest_logs[0]["records_dropped"] == 0
    assert ingest_logs[0]["drop_reason"] is None
    assert ingest_logs[0]["duration_ms"] >= 0.0


def test_ingest_drop_reason_set_on_duplicates() -> None:
    con = duckdb.connect()
    session_id = str(uuid.uuid4())
    sources = _sources(3)
    for s in sources:
        s["session_id"] = session_id

    # First ingest — loads all 3
    ingest(con, sources, session_id=session_id)

    # Second ingest with same sources — all 3 are duplicates
    with structlog.testing.capture_logs() as logs:
        ingest(con, sources, session_id=session_id)

    ingest_logs = [lg for lg in logs if lg.get("stage_name") == "ingest"]
    assert len(ingest_logs) == 1
    assert ingest_logs[0]["records_dropped"] == 3
    assert ingest_logs[0]["drop_reason"] == "duplicate_id"


def test_deduplicate_stage_log_event_name() -> None:
    con = duckdb.connect()
    session_id = str(uuid.uuid4())
    sources = _sources(4)
    for s in sources:
        s["session_id"] = session_id

    ingest(con, sources, session_id=session_id)

    with structlog.testing.capture_logs() as logs:
        deduplicate(con, session_id=session_id)

    dedup_logs = [lg for lg in logs if lg.get("stage_name") == "deduplicate"]
    assert len(dedup_logs) == 1
    assert dedup_logs[0]["event"] == "pipeline_stage_complete"
    assert dedup_logs[0]["session_id"] == session_id
    assert dedup_logs[0]["duration_ms"] >= 0.0


def test_score_stage_log_event_name() -> None:
    con = duckdb.connect()
    session_id = str(uuid.uuid4())
    sources = _sources(4)
    for s in sources:
        s["session_id"] = session_id

    ingest(con, sources, session_id=session_id)
    deduplicate(con, session_id=session_id)

    with structlog.testing.capture_logs() as logs:
        score(con, session_id=session_id)

    score_logs = [lg for lg in logs if lg.get("stage_name") == "score"]
    assert len(score_logs) == 1
    assert score_logs[0]["event"] == "pipeline_stage_complete"
    assert score_logs[0]["session_id"] == session_id
    assert score_logs[0]["duration_ms"] >= 0.0
