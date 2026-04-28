from typing import TypedDict


class PipelineStageLog(TypedDict):
    """
    Structured log record emitted by each pipeline stage on completion.
    All five stages must emit exactly one record of this type.

    Emit via:
        import structlog
        log = structlog.get_logger()
        log.info("pipeline_stage_complete", **stage_log)
    """

    stage_name: str
    session_id: str
    records_in: int
    records_out: int
    records_dropped: int
    drop_reason: str | None
    duration_ms: float
    extra: dict | None  # type: ignore[type-arg]


def validate_stage_log(log: PipelineStageLog) -> None:
    """Validate a PipelineStageLog record. Raises AssertionError on violation."""
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
