"""RAG retrieval service for Meridian Research.

Embeds a user question with all-MiniLM-L6-v2 and retrieves the top-5 matching
chunks from the Qdrant 'research_sources' collection (score_threshold=0.7).
Degrades gracefully to an empty list if the collection does not exist or the
search fails.
"""

from typing import Any

import structlog
from pydantic import BaseModel
from qdrant_client import QdrantClient

logger = structlog.get_logger(__name__)

_EMBEDDER: Any = None  # SentenceTransformer, imported lazily to avoid torch DLL issues


def _get_embedder() -> Any:
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer

        _EMBEDDER = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _EMBEDDER


class RagContext(BaseModel):
    """A single retrieved context chunk from the Qdrant vector store."""

    source_id: str
    url: str
    content_snippet: str
    quality_score: float  # mapped from payload['relevance_score']
    relevance_score: float  # mapped from Qdrant search score (cosine similarity)


def get_context(question: str, qdrant_client: QdrantClient) -> list[RagContext]:
    """Retrieve the top-5 relevant context chunks for *question*.

    Args:
        question: The raw research question to embed and search.
        qdrant_client: An initialised QdrantClient instance.

    Returns:
        A list of up to 5 RagContext objects, or [] on error / no results.
    """
    try:
        embedder = _get_embedder()
        query_vector: list[float] = embedder.encode(
            [question], normalize_embeddings=True
        )[0].tolist()

        results = qdrant_client.search(
            collection_name="research_sources",
            query_vector=query_vector,
            limit=5,
            score_threshold=0.7,
        )
    except Exception as exc:
        logger.warning(
            "rag_service.search_failed",
            error=str(exc),
            question=question[:100],
        )
        return []

    if not results:
        return []

    contexts: list[RagContext] = []
    for hit in results:
        payload = hit.payload or {}
        contexts.append(
            RagContext(
                source_id=str(payload.get("source_id", "")),
                url=str(payload.get("url", "")),
                content_snippet=str(payload.get("content_snippet", "")),
                quality_score=float(payload.get("relevance_score", 0.0)),
                relevance_score=float(hit.score),
            )
        )
    return contexts
