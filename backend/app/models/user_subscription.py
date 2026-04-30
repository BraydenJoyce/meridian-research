"""SQLAlchemy ORM model for user_subscriptions table (ADR-008)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from app.models.base import Base


class UserSubscription(MappedAsDataclass, Base):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        CheckConstraint("plan IN ('free', 'pro')", name="ck_user_subscriptions_plan"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    reports_used_this_month: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        Text, nullable=True, unique=True, default=None
    )
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=None,
        init=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        default=None,
        init=False,
    )
