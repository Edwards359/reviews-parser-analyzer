from collections.abc import AsyncGenerator

from app.config import get_settings
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_settings = get_settings()
_engine: AsyncEngine = create_async_engine(_settings.database_url, echo=False, future=True, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(
    bind=_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def get_engine() -> AsyncEngine:
    return _engine


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
