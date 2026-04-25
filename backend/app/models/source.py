import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from app.models.base import Base


class Source(MappedAsDataclass, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("session_id", "url", name="uq_sources_session_url"),
        CheckConstraint(
            "relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1",
            name="ck_sources_relevance_score",
        ),
    )

    # Required fields first
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    sub_task_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Fields with defaults
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default_factory=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    cleaned_content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    relevance_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, default=None
    )
    entities: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=None)
    qdrant_point_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, default=None)
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
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
