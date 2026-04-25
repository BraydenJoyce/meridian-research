import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class SourceRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    url: str
    title: str | None
    domain: str | None
    sub_task_index: int
    relevance_score: Decimal | None
    entities: Any | None
    qdrant_point_id: uuid.UUID | None
    fetched_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
