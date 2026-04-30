"""milestone5: auth and billing — user_subscriptions table

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # user_subscriptions                                                   #
    # ------------------------------------------------------------------ #
    op.create_table(
        "user_subscriptions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),
        sa.Column(
            "plan",
            sa.String(length=20),
            server_default="free",
            nullable=False,
        ),
        sa.Column(
            "reports_used_this_month",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("stripe_subscription_id", sa.Text(), nullable=True),
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
            "plan IN ('free', 'pro')",
            name="ck_user_subscriptions_plan",
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("stripe_subscription_id", name="uq_user_subs_stripe_sub_id"),
    )

    op.create_index(
        "idx_user_subscriptions_stripe_customer_id",
        "user_subscriptions",
        ["stripe_customer_id"],
        postgresql_where=sa.text("stripe_customer_id IS NOT NULL"),
    )

    op.execute(
        """
        CREATE TRIGGER trg_user_subscriptions_updated_at
            BEFORE UPDATE ON user_subscriptions
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_user_subscriptions_updated_at ON user_subscriptions")
    op.drop_index(
        "idx_user_subscriptions_stripe_customer_id", table_name="user_subscriptions"
    )
    op.drop_table("user_subscriptions")
