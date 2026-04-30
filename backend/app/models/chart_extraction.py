"""SQLAlchemy ORM model for chart_extractions table (ADR-005 Section 5)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from app.models.base import Base


class ChartExtraction(MappedAsDataclass, Base):
    __tablename__ = "chart_extractions"
    __table_args__ = (
        CheckConstraint(
            "chart_type IN ('bar_chart','line_chart','pie_chart','scatter_plot','table')",
            name="ck_chart_extractions_chart_type",
        ),
        CheckConstraint(
            "doc_class_confidence IS NULL OR doc_class_confidence BETWEEN 0 AND 1",
            name="ck_chart_extractions_confidence",
        ),
    )

    # Required fields
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    chart_type: Mapped[str] = mapped_column(Text, nullable=False)
    key_insight: Mapped[str] = mapped_column(Text, nullable=False)
    series: Mapped[Any] = mapped_column(JSONB, nullable=False, default_factory=list)

    # Fields with defaults
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default_factory=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    x_axis: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    y_axis: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    doc_class_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True, default=None
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=None,
        init=False,
    )
