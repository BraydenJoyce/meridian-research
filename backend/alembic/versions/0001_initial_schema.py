"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # research_sessions                                                    #
    # ------------------------------------------------------------------ #
    op.create_table(
        "research_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("report_markdown", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sub_tasks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(question) BETWEEN 10 AND 2000",
            name="ck_research_sessions_question_length",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_research_sessions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Partial index: fast queue polling by status
    op.create_index(
        "idx_research_sessions_status",
        "research_sessions",
        ["status"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    # Partial index: future dashboard user lookups
    op.create_index(
        "idx_research_sessions_user_id",
        "research_sessions",
        ["user_id"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    # set_updated_at trigger function (PostgreSQL-specific)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_research_sessions_updated_at
            BEFORE UPDATE ON research_sessions
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )

    # ------------------------------------------------------------------ #
    # sources                                                              #
    # ------------------------------------------------------------------ #
    op.create_table(
        "sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("sub_task_index", sa.Integer(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("cleaned_content", sa.Text(), nullable=True),
        sa.Column("relevance_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("qdrant_point_id", sa.UUID(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1",
            name="ck_sources_relevance_score",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["research_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "url", name="uq_sources_session_url"),
    )

    op.create_index("idx_sources_session_id", "sources", ["session_id"])
    op.create_index(
        "idx_sources_session_sub_task", "sources", ["session_id", "sub_task_index"]
    )
    # The UniqueConstraint above covers idx_sources_session_url semantically.
    # ADR-002 names it as a UNIQUE INDEX; keep it aligned:
    op.create_index(
        "idx_sources_session_url",
        "sources",
        ["session_id", "url"],
        unique=True,
    )

    op.execute(
        """
        CREATE TRIGGER trg_sources_updated_at
            BEFORE UPDATE ON sources
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )

    # ------------------------------------------------------------------ #
    # agent_events                                                         #
    # ------------------------------------------------------------------ #
    op.create_table(
        "agent_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("agent_type", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "agent_type IN ('planner', 'web_search', 'etl', 'writer', 'system')",
            name="ck_agent_events_agent_type",
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'agent_started', 'agent_completed', 'agent_failed', "
            "'sub_task_started', 'sub_task_completed', 'source_fetched', "
            "'etl_progress', 'report_chunk', 'done', 'error')",
            name="ck_agent_events_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["research_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_agent_events_session_seq",
        "agent_events",
        ["session_id", "sequence_number"],
    )
    op.create_index(
        "idx_agent_events_session_seq_filter",
        "agent_events",
        ["session_id", "sequence_number"],
        postgresql_where=sa.text("sequence_number > 0"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index("idx_agent_events_session_seq_filter", table_name="agent_events")
    op.drop_index("idx_agent_events_session_seq", table_name="agent_events")
    op.drop_table("agent_events")

    op.execute("DROP TRIGGER IF EXISTS trg_sources_updated_at ON sources")
    op.drop_index("idx_sources_session_url", table_name="sources")
    op.drop_index("idx_sources_session_sub_task", table_name="sources")
    op.drop_index("idx_sources_session_id", table_name="sources")
    op.drop_table("sources")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_research_sessions_updated_at ON research_sessions"
    )
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.drop_index("idx_research_sessions_user_id", table_name="research_sessions")
    op.drop_index("idx_research_sessions_status", table_name="research_sessions")
    op.drop_table("research_sessions")
