from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.schemas.research_session import CreateResearchResponse, ResearchSessionCreate
from app.services import research_service

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
