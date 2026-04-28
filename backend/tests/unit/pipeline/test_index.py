import uuid
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from app.pipeline.deduplicate import deduplicate
from app.pipeline.index import (
    COLLECTION_NAME,
    _chunk_point_id,
    _chunk_text,
    ensure_collection,
    index,
)
from app.pipeline.ingest import ingest
from app.pipeline.score import score

SESSION_ID = str(uuid.uuid4())


def _source(url: str, content: str, domain: str = "reuters.com") -> dict:
    return {
        "id": uuid.uuid4(),
        "session_id": uuid.UUID(SESSION_ID),
        "url": url,
        "title": f"Title for {url}",
        "domain": domain,
        "sub_task_index": 0,
        "raw_content": content,
        "fetched_at": "2026-01-01",
    }


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def _mock_client(collection_exists: bool = True) -> MagicMock:
    client = MagicMock(spec=["get_collections", "create_collection", "upsert"])
    existing = MagicMock()
    existing.name = COLLECTION_NAME
    client.get_collections.return_value.collections = [existing] if collection_exists else []
    return client


def test_chunk_text_short_document() -> None:
    text = " ".join(["word"] * 100)
    assert len(_chunk_text(text)) == 1


def test_chunk_text_long_document() -> None:
    text = " ".join(["word"] * 1100)
    assert len(_chunk_text(text)) >= 2


def test_chunk_text_very_short_discarded() -> None:
    text = " ".join(["word"] * 30)
    assert _chunk_text(text) == []


def test_chunk_point_id_deterministic() -> None:
    assert _chunk_point_id("abc", 0) == _chunk_point_id("abc", 0)


def test_chunk_point_id_differs_by_index() -> None:
    assert _chunk_point_id("abc", 0) != _chunk_point_id("abc", 1)


def test_ensure_collection_creates_when_absent() -> None:
    client = _mock_client(collection_exists=False)
    ensure_collection(client)
    client.create_collection.assert_called_once()
    _, kwargs = client.create_collection.call_args
    assert kwargs["collection_name"] == COLLECTION_NAME


def test_ensure_collection_idempotent() -> None:
    client = _mock_client(collection_exists=True)
    ensure_collection(client)
    client.create_collection.assert_not_called()


def test_index_calls_upsert_with_required_payload_fields(con: duckdb.DuckDBPyConnection) -> None:
    long_content = (
        "Microsoft Corporation reported strong quarterly earnings. "
        "The company announced new products. Revenue grew significantly. "
    ) * 30
    sources = [_source("https://reuters.com/a1", long_content)]
    ingest(con, sources)
    deduplicate(con)
    score(con)

    client = _mock_client()
    import numpy as np

    with patch("app.pipeline.index._get_embedder") as mock_emb:
        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((10, 384), dtype="float32")
        mock_emb.return_value = mock_model
        chunks_indexed = index(con, client, session_id=SESSION_ID)

    assert chunks_indexed >= 1
    client.upsert.assert_called()
    first_points = client.upsert.call_args_list[0][1]["points"]
    payload = first_points[0].payload
    required = {
        "source_id", "session_id", "url", "domain", "title",
        "chunk_index", "chunk_count", "content_snippet", "indexed_at", "relevance_score",
    }
    missing = required - set(payload.keys())
    assert not missing, f"Missing payload fields: {missing}"


def test_index_idempotent(con: duckdb.DuckDBPyConnection) -> None:
    content = " ".join(["word"] * 200)
    sources = [_source("https://reuters.com/a1", content)]
    ingest(con, sources)
    deduplicate(con)
    score(con)

    import numpy as np

    client = _mock_client()
    with patch("app.pipeline.index._get_embedder") as mock_emb:
        mock_model = MagicMock()
        mock_model.encode.return_value = np.zeros((5, 384), dtype="float32")
        mock_emb.return_value = mock_model
        count1 = index(con, client, session_id=SESSION_ID)
        count2 = index(con, client, session_id=SESSION_ID)

    assert count1 == count2
