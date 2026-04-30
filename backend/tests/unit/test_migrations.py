"""Tests for Alembic migration files (t-039).

These tests verify migration files exist and contain the expected DDL keywords
without requiring a live database connection.
"""
from __future__ import annotations

from pathlib import Path

_VERSIONS_DIR = Path(__file__).parents[2] / "alembic" / "versions"


def _read_migration(filename: str) -> str:
    return (_VERSIONS_DIR / filename).read_text(encoding="utf-8")


def test_migration_0003_creates_chart_extractions_table() -> None:
    content = _read_migration("0003_milestone3_cv_pipeline.py")
    assert "chart_extractions" in content
    assert "upgrade" in content
    assert "downgrade" in content
    assert "source_type" in content
    assert "down_revision" in content
    assert '"0001"' in content


def test_migration_0004_adds_critique_json_column() -> None:
    content = _read_migration("0004_milestone4_agents.py")
    assert "critique_json" in content
    assert "quality_score" in content
    assert "upgrade" in content
    assert "downgrade" in content
    assert "down_revision" in content
    assert '"0003"' in content


def test_migration_0005_creates_user_subscriptions_table() -> None:
    content = _read_migration("0005_milestone5_billing.py")
    assert "user_subscriptions" in content
    assert "stripe_customer_id" in content
    assert "stripe_subscription_id" in content
    assert "reports_used_this_month" in content
    assert "upgrade" in content
    assert "downgrade" in content
    assert "down_revision" in content
    assert '"0004"' in content


def test_migration_chain_is_contiguous() -> None:
    """Verify the down_revision chain: 0003->0001, 0004->0003, 0005->0004."""
    m3 = _read_migration("0003_milestone3_cv_pipeline.py")
    m4 = _read_migration("0004_milestone4_agents.py")
    m5 = _read_migration("0005_milestone5_billing.py")

    assert 'down_revision: str | None = "0001"' in m3
    assert 'down_revision: str | None = "0003"' in m4
    assert 'down_revision: str | None = "0004"' in m5


def test_user_subscriptions_has_plan_column_with_default() -> None:
    content = _read_migration("0005_milestone5_billing.py")
    assert "plan" in content
    assert "free" in content
