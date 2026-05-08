"""revenue features: public sharing slug for research sessions

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-07 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_sessions",
        sa.Column("public_slug", sa.String(12), nullable=True),
    )
    op.add_column(
        "research_sessions",
        sa.Column(
            "is_public",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_research_sessions_public_slug",
        "research_sessions",
        ["public_slug"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_research_sessions_public_slug", table_name="research_sessions")
    op.drop_column("research_sessions", "is_public")
    op.drop_column("research_sessions", "public_slug")
