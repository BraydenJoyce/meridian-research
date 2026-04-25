import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AgentEventRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    agent_type: str
    event_type: str
    payload: Any
    sequence_number: int
    created_at: datetime

    model_config = {"from_attributes": True}
