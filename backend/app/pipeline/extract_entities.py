from __future__ import annotations

import re
import time
import uuid as _uuid

import duckdb
import spacy
import spacy.language
import structlog

logger = structlog.get_logger(__name__)

ORG_SUFFIXES = re.compile(
    r"\b([A-Z][A-Za-z0-9&\-\.]+(?:\s+[A-Z][A-Za-z0-9&\-\.]+)*"
    r"\s+(?:Inc|Corp|LLC|Ltd|Co|Group|Holdings|Technologies|Solutions|"
    r"Software|Analytics|Intelligence|Capital|Ventures|Partners|Networks|"
    r"Systems|Consulting|Services|Enterprises|International|Global)\.?)\b"
)
PERSON_PATTERN = re.compile(
    r"\b(?:Mr\.|Ms\.|Dr\.|CEO|CFO|CTO|President|Founder)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\b"
    r"|(?<!\w)([A-Z][a-z]+\s+[A-Z][a-z]+)(?=\s+(?:said|announced|stated|noted|added))"
)
PRODUCT_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9\-\.]+(?:\s+[A-Z][A-Za-z0-9\-\.]+){0,2})"
    r"(?:\s+(?:v\d|version|\d+\.\d+|Pro|Enterprise|Cloud|Platform|API|SDK))\b"
)
METRIC_PATTERN = re.compile(
    r"\b(\$\s*[\d,]+(?:\.\d+)?\s*(?:billion|million|trillion|B|M|T|K)?)"
    r"|\b([\d,]+(?:\.\d+)?%)"
    r"|\b([\d,]+(?:\.\d+)?\s*(?:billion|million|trillion)\s+(?:users|customers|revenue|ARR|MRR))\b",
    re.IGNORECASE,
)

CREATE_ENTITIES = """
CREATE TABLE IF NOT EXISTS entities (
    id              TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    value           TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.9,
    context         TEXT,
    PRIMARY KEY (source_id, entity_type, value)
)
"""

# Lazy-loaded spaCy model singleton
_NLP: spacy.language.Language | None = None


def _get_nlp() -> spacy.language.Language:
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


def _extract_context(text: str, match_start: int, match_end: int) -> str:
    """Extract sentence containing the match, up to 300 chars."""
    sent_start = text.rfind(".", 0, match_start)
    sent_start = 0 if sent_start == -1 else sent_start + 1
    sent_end = text.find(".", match_end)
    sent_end = len(text) if sent_end == -1 else sent_end + 1
    return text[sent_start:sent_end].strip()[:300]


def extract_entities(con: duckdb.DuckDBPyConnection, session_id: str = "") -> int:
    t0 = time.perf_counter()
    con.execute(CREATE_ENTITIES)

    all_rows = con.execute("SELECT id, raw_content FROM scored_sources").fetchall()
    records_in = len(all_rows)

    quality_rows = con.execute(
        "SELECT id, raw_content FROM scored_sources WHERE quality_score >= 0.4"
    ).fetchall()
    records_dropped = records_in - len(quality_rows)

    nlp = _get_nlp()

    all_entities: list[tuple[str, str, str, str, float, str | None]] = []
    for source_id, content in quality_rows:
        if not content:
            continue
        seen: set[tuple[str, str]] = set()

        # spaCy NER for ORG and PERSON
        doc = nlp(content)
        for sent in doc.sents:
            for ent in sent.ents:
                if ent.label_ not in {"ORG", "PERSON"}:
                    continue
                val = ent.text.strip()
                if not val:
                    continue
                k = (ent.label_, val)
                if k not in seen:
                    seen.add(k)
                    ctx: str | None = doc[sent.start : sent.end].text[:300]
                    all_entities.append(
                        (str(_uuid.uuid4()), str(source_id), ent.label_, val, 0.85, ctx)
                    )

        # Regex fallback for ORG (via ORG_SUFFIXES) to preserve existing behaviour
        for m in ORG_SUFFIXES.finditer(content):
            val = m.group(1).strip()
            k = ("ORG", val)
            if k not in seen:
                seen.add(k)
                ctx = _extract_context(content, m.start(), m.end())
                all_entities.append(
                    (str(_uuid.uuid4()), str(source_id), "ORG", val, 0.9, ctx)
                )

        # Regex fallback for PERSON
        for m in PERSON_PATTERN.finditer(content):
            val = (m.group(1) or m.group(2) or "").strip()
            if not val:
                continue
            k = ("PERSON", val)
            if k not in seen:
                seen.add(k)
                ctx = _extract_context(content, m.start(), m.end())
                all_entities.append(
                    (str(_uuid.uuid4()), str(source_id), "PERSON", val, 0.9, ctx)
                )

        for m in PRODUCT_PATTERN.finditer(content):
            val = m.group(1).strip()
            k = ("PRODUCT", val)
            if k not in seen:
                seen.add(k)
                ctx = _extract_context(content, m.start(), m.end())
                all_entities.append(
                    (str(_uuid.uuid4()), str(source_id), "PRODUCT", val, 0.9, ctx)
                )

        for m in METRIC_PATTERN.finditer(content):
            val = next(filter(None, m.groups()), "").strip()
            if not val:
                continue
            k = ("METRIC", val)
            if k not in seen:
                seen.add(k)
                ctx = _extract_context(content, m.start(), m.end())
                all_entities.append(
                    (str(_uuid.uuid4()), str(source_id), "METRIC", val, 0.9, ctx)
                )

    existing_keys = {
        (r[0], r[1])
        for r in con.execute("SELECT source_id, value FROM entities").fetchall()
    }
    new_entities = [e for e in all_entities if (e[1], e[3]) not in existing_keys]

    if new_entities:
        con.executemany(
            "INSERT OR IGNORE INTO entities VALUES (?, ?, ?, ?, ?, ?)",
            new_entities,
        )

    records_out = int(con.execute("SELECT COUNT(*) FROM entities").fetchone()[0])  # type: ignore[index]
    duration_ms = (time.perf_counter() - t0) * 1000.0

    drop_reason: str | None = "below_quality_threshold" if records_dropped > 0 else None

    logger.info(
        "pipeline_stage_complete",
        stage_name="extract_entities",
        session_id=session_id,
        records_in=records_in,
        records_out=len(quality_rows),
        records_dropped=records_dropped,
        drop_reason=drop_reason,
        duration_ms=duration_ms,
        extra={"entity_count": records_out, "model": "en_core_web_sm"},
    )
    return records_out
