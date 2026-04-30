"""Smoke test that the launch checklist exists and is complete (t-051)."""
from __future__ import annotations

import pathlib


CHECKLIST = pathlib.Path(__file__).parents[3] / "docs" / "launch_checklist.md"


def test_launch_checklist_file_exists() -> None:
    assert CHECKLIST.exists(), "docs/launch_checklist.md is missing"


def test_launch_checklist_is_markdown() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    assert text.startswith("#"), "checklist must be a markdown file starting with a heading"


def test_launch_checklist_has_checked_items() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    checked = [line for line in text.splitlines() if line.strip().startswith("- [x]")]
    assert len(checked) >= 20, f"expected at least 20 checked items, found {len(checked)}"


def test_launch_checklist_covers_test_results() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    assert "165 passed" in text or "passed" in text
    assert "coverage" in text.lower()


def test_launch_checklist_covers_security() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    assert "Security" in text
    assert "JWT" in text
    assert "CORS" in text
