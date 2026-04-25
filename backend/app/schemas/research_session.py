import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResearchSessionCreate(BaseModel):
    question: str = Field(min_length=10, max_length=2000)


class ResearchSessionRead(BaseModel):
    id: uuid.UUID
    question: str
    status: str
    report_markdown: str | None
    error_message: str | None
    sub_tasks: Any | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class CreateResearchResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    stream_url: str
