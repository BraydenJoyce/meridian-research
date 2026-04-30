import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api import billing, health, research
from app.core.middleware import register_middleware
from app.services import worker

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    task = asyncio.create_task(worker.run_forever())
    logger.info("app.started")
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    logger.info("app.stopped")


app = FastAPI(
    title="Meridian Research API",
    version="0.1.0",
    lifespan=lifespan,
)

register_middleware(app)

app.include_router(health.router)
app.include_router(research.router)
app.include_router(billing.router)
