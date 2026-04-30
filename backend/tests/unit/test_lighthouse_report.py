"""Tests verifying the Lighthouse report file exists (t-044)."""
from __future__ import annotations

from pathlib import Path

_DOCS_DIR = Path(__file__).parents[3] / "docs"
_REPORT_PATH = _DOCS_DIR / "lighthouse_report.html"


def test_lighthouse_report_file_exists() -> None:
    assert _REPORT_PATH.exists(), f"Expected {_REPORT_PATH} to exist"
    assert _REPORT_PATH.stat().st_size > 0, "Lighthouse report is empty"


def test_lighthouse_report_is_html() -> None:
    content = _REPORT_PATH.read_text(encoding="utf-8")
    assert "<html" in content.lower(), "File does not appear to be HTML"
    assert "lighthouse" in content.lower(), "File does not contain Lighthouse data"


def test_lighthouse_report_documents_scores() -> None:
    content = _REPORT_PATH.read_text(encoding="utf-8")
    assert "LIGHTHOUSE AUDIT SCORES" in content
    assert "Accessibility" in content
