"""Pipeline benchmark: 1000 sources end-to-end, asserts < 60 seconds."""

# ruff: noqa: S311  # benchmark uses seeded random for reproducible synthetic data

from __future__ import annotations

import random
import time
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import numpy as np

from app.pipeline.deduplicate import deduplicate
from app.pipeline.extract_entities import extract_entities
from app.pipeline.index import index
from app.pipeline.ingest import ingest
from app.pipeline.score import score

TOTAL_SOURCES = 1000
DUP_FRACTION = 0.20
RESULTS_PATH = "C:/Projects/meridian-research/benchmark_results.md"

DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "medium.com",
    "reddit.com",
    "gov.uk",
    "arxiv.org",
]

# Meaningful-looking words so scoring factors (entity density, citations, etc.) work
_WORDS = (
    "market analysis research report findings indicate significant growth revenue "
    "billion million profit loss quarterly annual technology innovation platform "
    "investment strategy acquisition merger partnership development framework "
    "intelligence data analytics performance benchmark results sector industry "
    "government policy regulation compliance standard enterprise solution cloud "
    "artificial intelligence machine learning model training inference deployment "
    "financial services banking insurance asset management portfolio allocation "
    "consumer demand supply chain logistics distribution global international "
    "startup venture capital funding round valuation equity stake shareholder "
    "revenue ARR MRR growth rate churn retention customer acquisition cost "
    "product roadmap feature release version update patch improvement milestone"
).split()

_TITLE_WORDS = (
    "Report Analysis Overview Update Findings Outlook Benchmark Review Summary "
    "Q1 Q2 Q3 Q4 Annual Mid-Year Sector Market Global Regional"
).split()


def _make_sources(n: int) -> list[dict[str, Any]]:
    """
    Generate n synthetic source records.

    ~20% (DUP_FRACTION) are near-duplicates: 85-90% identical to a random
    earlier source - achieved by copying the base text and replacing ~12% of
    words with synonyms from the same word pool.
    """
    rng = random.Random(42)
    session_id = uuid.uuid4()
    sources: list[dict[str, Any]] = []
    base_contents: list[str] = []  # originals only, for dup seeding

    dup_count = int(n * DUP_FRACTION)
    original_count = n - dup_count

    # Build originals first
    for i in range(original_count):
        word_count = rng.randint(200, 500)
        domain = rng.choice(DOMAINS)
        title = f"{rng.choice(_TITLE_WORDS)} {rng.choice(_TITLE_WORDS)} {i}"
        content = " ".join(rng.choice(_WORDS) for _ in range(word_count))
        base_contents.append(content)
        sources.append(
            {
                "id": uuid.uuid4(),
                "session_id": session_id,
                "url": f"https://{domain}/article/{i}",
                "title": title,
                "domain": domain,
                "sub_task_index": i % 10,
                "raw_content": content,
                "fetched_at": "2026-01-15T10:00:00",
            }
        )

    # Build near-duplicates (85-90% overlap)
    for j in range(dup_count):
        base = rng.choice(base_contents)
        words = base.split()
        # Replace 10-15% of words to get 85-90% overlap
        replace_frac = rng.uniform(0.10, 0.15)
        num_replace = max(1, int(len(words) * replace_frac))
        positions = rng.sample(range(len(words)), min(num_replace, len(words)))
        words_copy = list(words)
        for pos in positions:
            words_copy[pos] = rng.choice(_WORDS)
        domain = rng.choice(DOMAINS)
        idx = original_count + j
        title = f"Duplicate {rng.choice(_TITLE_WORDS)} {idx}"
        sources.append(
            {
                "id": uuid.uuid4(),
                "session_id": session_id,
                "url": f"https://{domain}/dup/{j}",
                "title": title,
                "domain": domain,
                "sub_task_index": j % 10,
                "raw_content": " ".join(words_copy),
                "fetched_at": "2026-01-15T10:00:00",
            }
        )

    rng.shuffle(sources)
    return sources


def _mock_qdrant() -> MagicMock:
    """Return a MagicMock that satisfies ensure_collection and index."""
    mock_client: MagicMock = MagicMock()
    # ensure_collection checks client.get_collections().collections
    mock_collections_response = MagicMock()
    mock_collections_response.collections = []
    mock_client.get_collections.return_value = mock_collections_response
    # upsert is a no-op — default MagicMock behaviour is sufficient
    return mock_client


def run_benchmark() -> dict[str, Any]:
    """Run full pipeline on 1000 synthetic sources. Returns timing + record counts."""
    sources = _make_sources(TOTAL_SOURCES)

    mock_qdrant_client = _mock_qdrant()

    # Mock embedder: returns zero-vectors of correct shape
    mock_model: MagicMock = MagicMock()
    mock_model.encode.side_effect = lambda texts, **kwargs: np.zeros(  # type: ignore[misc]
        (len(texts), 384), dtype="float32"
    )

    # Mock spaCy nlp: returns docs with no entities
    mock_nlp: MagicMock = MagicMock()

    def _mock_nlp_call(text: str) -> MagicMock:  # type: ignore[misc]
        doc = MagicMock()
        doc.sents = []
        doc.ents = []
        return doc

    mock_nlp.side_effect = _mock_nlp_call

    timings: dict[str, float] = {}
    counts: dict[str, int] = {}

    con = duckdb.connect()
    session_id = str(sources[0]["session_id"]) if sources else ""

    with (
        patch("app.pipeline.index._get_embedder", return_value=mock_model),
        patch("app.pipeline.extract_entities._get_nlp", return_value=mock_nlp),
    ):
        # ── ingest ──────────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        ingested = ingest(con, sources, session_id=session_id)
        timings["ingest"] = time.perf_counter() - t0
        counts["ingested"] = ingested

        # ── deduplicate ─────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        deduped = deduplicate(con, session_id=session_id)
        timings["deduplicate"] = time.perf_counter() - t0
        counts["deduped"] = deduped

        # ── score ────────────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        scored = score(con, session_id=session_id)
        timings["score"] = time.perf_counter() - t0
        counts["scored"] = scored

        # ── extract_entities ────────────────────────────────────────────────────
        t0 = time.perf_counter()
        entity_count = extract_entities(con, session_id=session_id)
        timings["extract_entities"] = time.perf_counter() - t0
        counts["entities"] = entity_count

        # ── index ────────────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        indexed = index(con, mock_qdrant_client, session_id=session_id)
        timings["index"] = time.perf_counter() - t0
        counts["indexed"] = indexed

    con.close()

    total_time = sum(timings.values())
    dedup_rate = (
        (counts["ingested"] - counts["deduped"]) / counts["ingested"] * 100.0
        if counts["ingested"] > 0
        else 0.0
    )

    return {
        "total_time": total_time,
        "timings": timings,
        "counts": counts,
        "dedup_rate": dedup_rate,
    }


def _write_results(results: dict[str, Any]) -> None:
    total = results["total_time"]
    timings: dict[str, float] = results["timings"]
    counts: dict[str, int] = results["counts"]
    dedup_rate: float = results["dedup_rate"]

    lines = [
        "# Pipeline Benchmark Results",
        "",
        f"**Total time:** {total:.3f} seconds",
        f"**Assert < 60 s:** {'PASS' if total < 60 else 'FAIL'}",
        "",
        "## Per-Stage Breakdown",
        "",
        "| Stage | Time (s) | Records |",
        "|---|---|---|",
        f"| ingest | {timings['ingest']:.3f} | {counts['ingested']} ingested |",
        f"| deduplicate | {timings['deduplicate']:.3f} | {counts['deduped']} after dedup |",
        f"| score | {timings['score']:.3f} | {counts['scored']} after scoring |",
        f"| extract_entities | {timings['extract_entities']:.3f} | {counts['entities']} entities |",
        f"| index | {timings['index']:.3f} | {counts['indexed']} chunks indexed |",
        "",
        "## Summary Statistics",
        "",
        f"- **Sources ingested:** {counts['ingested']}",
        f"- **Sources after dedup:** {counts['deduped']}",
        f"- **Sources after scoring:** {counts['scored']}",
        f"- **Entities extracted:** {counts['entities']}",
        f"- **Chunks indexed:** {counts['indexed']}",
        f"- **Dedup rate:** {dedup_rate:.1f}% duplicates removed",
        "",
    ]
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    results = run_benchmark()

    total = results["total_time"]
    timings: dict[str, float] = results["timings"]
    counts: dict[str, int] = results["counts"]
    dedup_rate: float = results["dedup_rate"]

    _write_results(results)

    print("=" * 60)
    print("PIPELINE BENCHMARK RESULTS")
    print("=" * 60)
    print(f"Total time:        {total:.3f}s")
    print(f"Assert < 60s:      {'PASS' if total < 60 else 'FAIL'}")
    print()
    print("Per-stage:")
    for stage, t in timings.items():
        print(f"  {stage:<20} {t:.3f}s")
    print()
    print("Record counts:")
    print(f"  ingested:          {counts['ingested']}")
    print(f"  after dedup:       {counts['deduped']}")
    print(f"  after scoring:     {counts['scored']}")
    print(f"  entities:          {counts['entities']}")
    print(f"  chunks indexed:    {counts['indexed']}")
    print(f"  dedup rate:        {dedup_rate:.1f}%")
    print("=" * 60)
    print(f"Results written to: {RESULTS_PATH}")

    assert total < 60, f"Benchmark exceeded 60s limit: {total:.3f}s"
    print("Assertion PASSED: total time < 60s")
