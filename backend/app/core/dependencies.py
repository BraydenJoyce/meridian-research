from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.db import AsyncSessionFactory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session
