"""milestone3: cv pipeline — chart_extractions table + sources.source_type

Revision ID: 0003
Revises: 0001
Create Date: 2026-04-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # chart_extractions                                                    #
    # ------------------------------------------------------------------ #
    op.create_table(
        "chart_extractions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("chart_type", sa.Text(), nullable=False),
        sa.Column("key_insight", sa.Text(), nullable=False),
        sa.Column(
            "series",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("x_axis", sa.Text(), nullable=True),
        sa.Column("y_axis", sa.Text(), nullable=True),
        sa.Column("doc_class_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chart_type IN ('bar_chart','line_chart','pie_chart','scatter_plot','table')",
            name="ck_chart_extractions_chart_type",
        ),
        sa.CheckConstraint(
            "doc_class_confidence IS NULL OR doc_class_confidence BETWEEN 0 AND 1",
            name="ck_chart_extractions_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["research_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_chart_extractions_session_id", "chart_extractions", ["session_id"]
    )

    # ------------------------------------------------------------------ #
    # sources.source_type                                                  #
    # ------------------------------------------------------------------ #
    op.add_column(
        "sources",
        sa.Column("source_type", sa.String(length=20), nullable=True),
    )

    op.create_index(
        "idx_sources_source_type",
        "sources",
        ["source_type"],
        postgresql_where=sa.text("source_type IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_sources_source_type", table_name="sources")
    op.drop_column("sources", "source_type")

    op.drop_index("idx_chart_extractions_session_id", table_name="chart_extractions")
    op.drop_table("chart_extractions")
