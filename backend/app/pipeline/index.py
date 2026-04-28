"""Qdrant vector indexing stage for the Meridian Research ETL pipeline.

Chunks source content, embeds with all-MiniLM-L6-v2, and upserts to Qdrant
collection 'research_sources' (384-dim, Cosine). Point IDs are deterministic
(UUID v5 from source_id + chunk_index) making re-indexing idempotent.
"""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import duckdb
import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

logger = structlog.get_logger(__name__)

COLLECTION_NAME = "research_sources"
QDRANT_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

_EMBEDDER: Any = None  # SentenceTransformer, imported lazily to avoid torch DLL issues


def _get_embedder() -> Any:
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer

        _EMBEDDER = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _EMBEDDER


def _chunk_point_id(source_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(QDRANT_NAMESPACE, f"{source_id}:{chunk_index}"))


def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [text] if len(words) >= 50 else []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_words = words[start:end]
        if len(chunk_words) >= 50:
            chunks.append(" ".join(chunk_words))
        if end >= len(words):
            break
        start += chunk_size - overlap
    return chunks


def ensure_collection(client: QdrantClient) -> None:
    """Create research_sources collection if it does not exist. Idempotent."""
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )


def index(
    con: duckdb.DuckDBPyConnection,
    client: QdrantClient,
    session_id: str = "",
    *,
    batch_size: int = 64,
) -> int:
    """Embed all scored sources and upsert chunks to Qdrant. Returns chunk count."""
    t0 = time.perf_counter()

    ensure_collection(client)

    rows = con.execute(
        "SELECT id, url, domain, title, sub_task_index, raw_content, quality_score "
        "FROM scored_sources"
    ).fetchall()
    records_in = len(rows)

    all_chunks: list[dict[str, Any]] = []
    for source_id, url, domain, title, sub_task_index, raw_content, quality_score in rows:
        if not raw_content:
            continue
        chunks = _chunk_text(raw_content)
        chunk_count = len(chunks)
        for chunk_index, chunk_text in enumerate(chunks):
            all_chunks.append(
                {
                    "point_id": _chunk_point_id(str(source_id), chunk_index),
                    "text": chunk_text,
                    "payload": {
                        "source_id": str(source_id),
                        "session_id": session_id,
                        "url": url,
                        "domain": domain or "",
                        "title": title or "",
                        "sub_task_index": sub_task_index or 0,
                        "relevance_score": float(quality_score),
                        "chunk_index": chunk_index,
                        "chunk_count": chunk_count,
                        "content_snippet": chunk_text[:200],
                        "entity_types": [],
                        "indexed_at": datetime.now(UTC).isoformat(),
                    },
                }
            )

    if not all_chunks:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "pipeline_stage_complete",
            stage_name="index",
            session_id=session_id,
            records_in=records_in,
            records_out=0,
            records_dropped=records_in,
            drop_reason="no_content",
            duration_ms=duration_ms,
            extra={"collection": COLLECTION_NAME, "batch_size": batch_size},
        )
        return 0

    embedder = _get_embedder()
    texts = [c["text"] for c in all_chunks]
    embeddings = embedder.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )

    points = [
        PointStruct(
            id=chunk["point_id"],
            vector=embeddings[i].tolist(),
            payload=chunk["payload"],
        )
        for i, chunk in enumerate(all_chunks)
    ]

    for batch_start in range(0, len(points), batch_size):
        batch = points[batch_start : batch_start + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)

    duration_ms = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "pipeline_stage_complete",
        stage_name="index",
        session_id=session_id,
        records_in=records_in,
        records_out=len(all_chunks),
        records_dropped=0,
        drop_reason=None,
        duration_ms=duration_ms,
        extra={
            "collection": COLLECTION_NAME,
            "batch_size": batch_size,
            "chunks_total": len(all_chunks),
            "sources_indexed": records_in,
        },
    )
    return len(all_chunks)
