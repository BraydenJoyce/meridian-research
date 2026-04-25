import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.research_session import ResearchSession
from app.schemas.research_session import CreateResearchResponse, ResearchSessionCreate
from app.services import research_service
from app.services.stream_service import event_stream

router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("/create", response_model=CreateResearchResponse, status_code=202)
async def create_research(
    body: ResearchSessionCreate,
    db: AsyncSession = Depends(get_db),
) -> CreateResearchResponse:
    return await research_service.create_research_session(
        question=body.question,
        db=db,
    )


@router.get("/{session_id}/stream")
async def stream_research(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    result = await db.execute(
        select(ResearchSession).where(ResearchSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return StreamingResponse(
        event_stream(session_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
