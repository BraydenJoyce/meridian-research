import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from app.models.base import Base


class ResearchSession(MappedAsDataclass, Base):
    __tablename__ = "research_sessions"
    __table_args__ = (
        CheckConstraint(
            "char_length(question) BETWEEN 10 AND 2000",
            name="ck_research_sessions_question_length",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_research_sessions_status",
        ),
    )

    # Required fields first (no default)
    question: Mapped[str] = mapped_column(Text, nullable=False)

    # Fields with defaults
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default_factory=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    sub_tasks: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=None)
    critique_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=None)
    quality_score: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True, default=None
    )
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
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
