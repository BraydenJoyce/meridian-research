from typing import Any

import duckdb
import structlog

from app.pipeline.deduplicate import deduplicate
from app.pipeline.extract_entities import extract_entities
from app.pipeline.ingest import ingest
from app.pipeline.score import score

logger = structlog.get_logger(__name__)


def run_pipeline(sources: list[dict[str, Any]]) -> dict[str, Any]:
    con = duckdb.connect()
    try:
        ingested = ingest(con, sources)
        deduped = deduplicate(con)
        scored = score(con)
        entity_count = extract_entities(con)

        logger.info(
            "pipeline.completed",
            ingested=ingested,
            deduped=deduped,
            scored=scored,
            entity_count=entity_count,
        )
        return {
            "ingested": ingested,
            "deduped": deduped,
            "scored": scored,
            "entity_count": entity_count,
            "connection": con,
        }
    except Exception:
        con.close()
        raise
