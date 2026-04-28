from typing import Any

import duckdb
import structlog
from qdrant_client import QdrantClient

from app.pipeline.deduplicate import deduplicate
from app.pipeline.extract_entities import extract_entities
from app.pipeline.index import index
from app.pipeline.ingest import ingest
from app.pipeline.score import score

logger = structlog.get_logger(__name__)


def run_pipeline(
    sources: list[dict[str, Any]],
    qdrant_client: QdrantClient | None = None,
) -> dict[str, Any]:
    con = duckdb.connect()
    session_id = str(sources[0]["session_id"]) if sources else ""
    try:
        ingested = ingest(con, sources)
        deduped = deduplicate(con, session_id=session_id)
        scored = score(con, session_id=session_id)
        entity_count = extract_entities(con, session_id=session_id)

        indexed = 0
        if qdrant_client is not None:
            indexed = index(con, qdrant_client, session_id=session_id)

        logger.info(
            "pipeline.completed",
            ingested=ingested,
            deduped=deduped,
            scored=scored,
            entity_count=entity_count,
            indexed=indexed,
        )
        return {
            "ingested": ingested,
            "deduped": deduped,
            "scored": scored,
            "entity_count": entity_count,
            "indexed": indexed,
            "connection": con,
        }
    except Exception:
        con.close()
        raise
