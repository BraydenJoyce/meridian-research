"""Automated report quality scoring: citation density and readability metrics (ADR-007)."""
from __future__ import annotations

import re

import textstat
from pydantic import BaseModel, field_validator


class ReportQuality(BaseModel):
    word_count: int
    citation_count: int
    citation_density: float
    section_count: int
    flesch_kincaid_grade: float
    composite_score: float

    @field_validator("composite_score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


_CITATION_RE = re.compile(r"\[([^\]]+)\]\(https?://[^\)]+\)")
_SECTION_RE = re.compile(r"^##\s+.+", re.MULTILINE)
_WORD_RE = re.compile(r"\b\w+\b")

_MAX_CITATION_DENSITY = 5.0
_MAX_SECTIONS = 10


def score_report(markdown: str) -> ReportQuality:
    """Compute quality metrics for a markdown report string.

    Metrics computed:
        - word_count: total word tokens
        - citation_count: number of markdown hyperlinks
        - citation_density: citations per 100 words
        - section_count: number of ## headings
        - flesch_kincaid_grade: readability grade level (via textstat)
        - composite_score: 0.4*citation_density_norm + 0.3*section_norm + 0.3*readability_norm

    Args:
        markdown: Raw markdown text of the report.

    Returns:
        ReportQuality with all metrics populated. Returns zero scores for empty input.
    """
    if not markdown or not markdown.strip():
        return ReportQuality(
            word_count=0,
            citation_count=0,
            citation_density=0.0,
            section_count=0,
            flesch_kincaid_grade=0.0,
            composite_score=0.0,
        )

    word_count = len(_WORD_RE.findall(markdown))
    citation_count = len(_CITATION_RE.findall(markdown))
    section_count = len(_SECTION_RE.findall(markdown))

    citations_per_100 = (citation_count / word_count * 100) if word_count > 0 else 0.0
    citation_density = round(citations_per_100, 4)

    plain_text = _CITATION_RE.sub(r"\1", markdown)
    plain_text = re.sub(r"^#+\s*", "", plain_text, flags=re.MULTILINE)
    plain_text = re.sub(r"\*+", "", plain_text)
    try:
        fk_grade = float(textstat.flesch_kincaid_grade(plain_text))
    except Exception:
        fk_grade = 0.0

    citation_density_norm = min(citation_density / _MAX_CITATION_DENSITY, 1.0)
    section_norm = min(section_count / _MAX_SECTIONS, 1.0)
    readability_norm = max(0.0, min(1.0, 1.0 - (fk_grade - 8.0) / 12.0))

    composite = (
        0.4 * citation_density_norm
        + 0.3 * section_norm
        + 0.3 * readability_norm
    )

    return ReportQuality(
        word_count=word_count,
        citation_count=citation_count,
        citation_density=citation_density,
        section_count=section_count,
        flesch_kincaid_grade=round(fk_grade, 2),
        composite_score=round(composite, 4),
    )
