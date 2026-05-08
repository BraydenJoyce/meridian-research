import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from app.models.base import Base


class AgentEvent(MappedAsDataclass, Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        CheckConstraint(
            "agent_type IN ("
            "'planner', 'web_search', 'cv_document', 'news', 'structured_data', "
            "'etl', 'writer', 'critic', 'orchestrator', 'system', "
            "'hypothesis', 'metrics', 'chart_gallery', 'strategist')",
            name="ck_agent_events_agent_type",
        ),
        CheckConstraint(
            "event_type IN ("
            "'agent_started', 'agent_completed', 'agent_failed', "
            "'sub_task_started', 'sub_task_completed', 'source_fetched', "
            "'etl_progress', 'report_chunk', 'report_complete', "
            "'report_critique', 'news_fetched', 'edgar_fetched', "
            "'cv_document_started', 'cv_document_classified', "
            "'cv_chart_extracted', 'orchestration_summary', 'done', 'error', "
            "'hypothesis_ready', 'metrics_ready', 'chart_gallery_ready', 'strategy_ready')",
            name="ck_agent_events_event_type",
        ),
        Index("idx_agent_events_session_seq", "session_id", "sequence_number"),
    )

    # Required fields first
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Fields with defaults
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default_factory=uuid.uuid4)
    payload: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default="{}", default_factory=dict
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=None,
        init=False,
    )
