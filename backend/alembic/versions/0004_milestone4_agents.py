"""milestone4: multi-agent expansion — critique_json and quality_score columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # research_sessions.critique_json                                      #
    # ------------------------------------------------------------------ #
    op.add_column(
        "research_sessions",
        sa.Column(
            "critique_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------ #
    # research_sessions.quality_score                                      #
    # ------------------------------------------------------------------ #
    op.add_column(
        "research_sessions",
        sa.Column("quality_score", sa.Numeric(precision=4, scale=3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_sessions", "quality_score")
    op.drop_column("research_sessions", "critique_json")
