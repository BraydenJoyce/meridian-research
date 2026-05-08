"""add innovation team agents: hypothesis, metrics, chart_gallery, strategist

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-07 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AGENT_TYPE_CHECK = (
    "agent_type IN ("
    "'planner', 'web_search', 'cv_document', 'news', 'structured_data', "
    "'etl', 'writer', 'critic', 'orchestrator', 'system', "
    "'hypothesis', 'metrics', 'chart_gallery', 'strategist')"
)

EVENT_TYPE_CHECK = (
    "event_type IN ("
    "'agent_started', 'agent_completed', 'agent_failed', "
    "'sub_task_started', 'sub_task_completed', 'source_fetched', "
    "'etl_progress', 'report_chunk', 'report_complete', "
    "'report_critique', 'news_fetched', 'edgar_fetched', "
    "'cv_document_started', 'cv_document_classified', "
    "'cv_chart_extracted', 'orchestration_summary', 'done', 'error', "
    "'hypothesis_ready', 'metrics_ready', 'chart_gallery_ready', 'strategy_ready')"
)

LEGACY_AGENT_TYPE_CHECK = (
    "agent_type IN ("
    "'planner', 'web_search', 'cv_document', 'news', 'structured_data', "
    "'etl', 'writer', 'critic', 'orchestrator', 'system')"
)

LEGACY_EVENT_TYPE_CHECK = (
    "event_type IN ("
    "'agent_started', 'agent_completed', 'agent_failed', "
    "'sub_task_started', 'sub_task_completed', 'source_fetched', "
    "'etl_progress', 'report_chunk', 'report_complete', "
    "'report_critique', 'news_fetched', 'edgar_fetched', "
    "'cv_document_started', 'cv_document_classified', "
    "'cv_chart_extracted', 'orchestration_summary', 'done', 'error')"
)


def upgrade() -> None:
    # Add new JSONB columns to research_sessions
    op.add_column(
        "research_sessions",
        sa.Column("hypothesis_json", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "research_sessions",
        sa.Column("metrics_json", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "research_sessions",
        sa.Column("strategy_json", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "research_sessions",
        sa.Column("chart_gallery_json", postgresql.JSONB(), nullable=True),
    )

    # Expand agent_type and event_type constraints
    op.drop_constraint("ck_agent_events_agent_type", "agent_events", type_="check")
    op.drop_constraint("ck_agent_events_event_type", "agent_events", type_="check")
    op.create_check_constraint(
        "ck_agent_events_agent_type",
        "agent_events",
        sa.text(AGENT_TYPE_CHECK),
    )
    op.create_check_constraint(
        "ck_agent_events_event_type",
        "agent_events",
        sa.text(EVENT_TYPE_CHECK),
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_events_agent_type", "agent_events", type_="check")
    op.drop_constraint("ck_agent_events_event_type", "agent_events", type_="check")
    op.create_check_constraint(
        "ck_agent_events_agent_type",
        "agent_events",
        sa.text(LEGACY_AGENT_TYPE_CHECK),
    )
    op.create_check_constraint(
        "ck_agent_events_event_type",
        "agent_events",
        sa.text(LEGACY_EVENT_TYPE_CHECK),
    )

    op.drop_column("research_sessions", "chart_gallery_json")
    op.drop_column("research_sessions", "strategy_json")
    op.drop_column("research_sessions", "metrics_json")
    op.drop_column("research_sessions", "hypothesis_json")
