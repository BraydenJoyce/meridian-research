import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.models.research_session import ResearchSession
from app.schemas.research_session import CreateResearchResponse, ResearchSessionCreate
from app.services import research_service
from app.services.report_generator import generate_pdf
from app.services.stream_service import event_stream

router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("/create", response_model=CreateResearchResponse, status_code=202)
async def create_research(
    body: ResearchSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
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


@router.get("/{session_id}/export")
async def export_report(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    result = await db.execute(
        select(ResearchSession).where(ResearchSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None or session.report_markdown is None:
        raise HTTPException(status_code=404, detail="Report not found")

    pdf_bytes = generate_pdf(session.report_markdown)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=report.pdf"},
    )
