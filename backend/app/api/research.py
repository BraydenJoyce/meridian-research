import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.models.research_session import ResearchSession
from app.schemas.research_session import CreateResearchResponse, ResearchSessionCreate
from app.services import research_service
from app.services.report_generator import generate_pdf
from app.services.stream_service import event_stream

router = APIRouter(prefix="/api/research", tags=["research"])


@router.post("/create", response_model=CreateResearchResponse, status_code=202)
@limiter.limit("10/minute")
async def create_research(
    request: Request,
    body: ResearchSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CreateResearchResponse:
    """Create a new research session and enqueue it for processing.

    Args:
        body: Research question (10-2000 characters).
        db: Async database session.
        current_user: Authenticated user from JWT.

    Returns:
        Session ID, initial status, and SSE stream URL.

    Raises:
        HTTPException(429): Free-tier monthly limit reached.
    """
    return await research_service.create_research_session(
        question=body.question,
        db=db,
        user_id=current_user.user_id,
    )


@router.get("/{session_id}/stream")
@limiter.limit("30/minute")
async def stream_research(
    request: Request,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream real-time agent trace events for a research session via SSE.

    Args:
        session_id: UUID of the research session to stream.
        db: Async database session.

    Returns:
        Server-Sent Events stream with agent trace events.

    Raises:
        HTTPException(404): Session not found.
    """
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
@limiter.limit("20/minute")
async def export_report(
    request: Request,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Export a completed research report as a PDF file.

    Args:
        session_id: UUID of the completed research session.
        db: Async database session.
        current_user: Authenticated user from JWT.

    Returns:
        PDF file as application/pdf response with Content-Disposition header.

    Raises:
        HTTPException(404): Session not found or report not yet generated.
    """
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
