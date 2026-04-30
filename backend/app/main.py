import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import billing, health, research
from app.core.config import get_settings
from app.core.middleware import register_middleware
from app.core.rate_limit import limiter
from app.services import worker

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)
        logger.info("sentry.initialized")

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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

register_middleware(app)

app.include_router(health.router)
app.include_router(research.router)
app.include_router(billing.router)
