"""Tests for quality_scorer service (t-035)."""
from __future__ import annotations

from app.services.quality_scorer import ReportQuality, score_report

_SAMPLE_REPORT = """## Executive Summary

The AI market grew significantly in 2024, driven by enterprise adoption.
[McKinsey Report](https://mckinsey.com/ai-2024) shows a 40% year-over-year increase.
Cloud providers like AWS and Azure reported strong AI revenue. [AWS Report](https://aws.com/q4)

## Market Analysis

Enterprise spending on AI reached $200B globally. [Gartner](https://gartner.com/ai-spend)
Large language models dominate the enterprise segment with 65% market share.
[OpenAI Report](https://openai.com/research)

## Conclusion

The AI market will continue growing. Investors should focus on infrastructure plays.
[Bloomberg](https://bloomberg.com/ai-infra)
"""


def test_citation_density_computed_correctly() -> None:
    result = score_report(_SAMPLE_REPORT)
    assert result.citation_count >= 4
    assert result.citation_density > 0.0


def test_section_count_computed_correctly() -> None:
    result = score_report(_SAMPLE_REPORT)
    assert result.section_count == 3


def test_composite_score_in_range() -> None:
    result = score_report(_SAMPLE_REPORT)
    assert 0.0 <= result.composite_score <= 1.0


def test_empty_report_returns_zero_scores() -> None:
    result = score_report("")
    assert result.word_count == 0
    assert result.citation_count == 0
    assert result.composite_score == 0.0


def test_report_quality_is_pydantic_model() -> None:
    result = score_report(_SAMPLE_REPORT)
    assert isinstance(result, ReportQuality)
    dumped = result.model_dump()
    assert "composite_score" in dumped
    assert "word_count" in dumped
    assert "flesch_kincaid_grade" in dumped
