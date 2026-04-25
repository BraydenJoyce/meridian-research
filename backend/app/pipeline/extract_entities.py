import re

import duckdb
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
    id          TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    value       TEXT NOT NULL,
    PRIMARY KEY (source_id, entity_type, value)
)
"""


def extract_entities(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(CREATE_ENTITIES)

    rows = con.execute("SELECT id, raw_content FROM scored_sources").fetchall()
    records_in = len(rows)

    import uuid as _uuid

    all_entities: list[tuple[str, str, str, str]] = []
    for source_id, content in rows:
        if not content:
            continue
        seen: set[tuple[str, str]] = set()

        for m in ORG_SUFFIXES.finditer(content):
            val = m.group(1).strip()
            k = ("ORG", val)
            if k not in seen:
                seen.add(k)
                all_entities.append((str(_uuid.uuid4()), source_id, "ORG", val))

        for m in PERSON_PATTERN.finditer(content):
            val = (m.group(1) or m.group(2) or "").strip()
            if not val:
                continue
            k = ("PERSON", val)
            if k not in seen:
                seen.add(k)
                all_entities.append((str(_uuid.uuid4()), source_id, "PERSON", val))

        for m in PRODUCT_PATTERN.finditer(content):
            val = m.group(1).strip()
            k = ("PRODUCT", val)
            if k not in seen:
                seen.add(k)
                all_entities.append((str(_uuid.uuid4()), source_id, "PRODUCT", val))

        for m in METRIC_PATTERN.finditer(content):
            val = next(filter(None, m.groups()), "").strip()
            if not val:
                continue
            k = ("METRIC", val)
            if k not in seen:
                seen.add(k)
                all_entities.append((str(_uuid.uuid4()), source_id, "METRIC", val))

    existing_keys = {
        (r[0], r[1])
        for r in con.execute("SELECT source_id, value FROM entities").fetchall()
    }
    new_entities = [
        e for e in all_entities if (e[1], e[3]) not in existing_keys
    ]

    if new_entities:
        con.executemany(
            "INSERT OR IGNORE INTO entities VALUES (?, ?, ?, ?)",
            new_entities,
        )

    records_out = int(con.execute("SELECT COUNT(*) FROM entities").fetchone()[0])  # type: ignore[index]

    logger.info(
        "pipeline.extract_entities",
        stage_name="extract_entities",
        records_in=records_in,
        records_out=records_out,
        records_dropped=0,
        reason=None,
    )
    return records_out
