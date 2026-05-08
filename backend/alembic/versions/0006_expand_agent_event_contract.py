"""expand agent event contract for multi-agent orchestration

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AGENT_TYPE_CHECK = (
    "agent_type IN ("
    "'planner', 'web_search', 'cv_document', 'news', 'structured_data', "
    "'etl', 'writer', 'critic', 'orchestrator', 'system')"
)

EVENT_TYPE_CHECK = (
    "event_type IN ("
    "'agent_started', 'agent_completed', 'agent_failed', "
    "'sub_task_started', 'sub_task_completed', 'source_fetched', "
    "'etl_progress', 'report_chunk', 'report_complete', "
    "'report_critique', 'news_fetched', 'edgar_fetched', "
    "'cv_document_started', 'cv_document_classified', "
    "'cv_chart_extracted', 'orchestration_summary', 'done', 'error')"
)

LEGACY_AGENT_TYPE_CHECK = (
    "agent_type IN ('planner', 'web_search', 'etl', 'writer', 'system')"
)

LEGACY_EVENT_TYPE_CHECK = (
    "event_type IN ("
    "'agent_started', 'agent_completed', 'agent_failed', "
    "'sub_task_started', 'sub_task_completed', 'source_fetched', "
    "'etl_progress', 'report_chunk', 'done', 'error')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_agent_events_agent_type",
        "agent_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_events_event_type",
        "agent_events",
        type_="check",
    )
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
    op.drop_constraint(
        "ck_agent_events_agent_type",
        "agent_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_events_event_type",
        "agent_events",
        type_="check",
    )
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
