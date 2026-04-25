import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_forever() -> None:
    """Background worker stub. Full implementation in pipeline/runner.py (t-003+)."""
    logger.info("worker.started")
    while True:
        await asyncio.sleep(5)
