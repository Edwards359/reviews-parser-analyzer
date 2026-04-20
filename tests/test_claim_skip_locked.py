"""Интеграционный тест атомарного claim с FOR UPDATE SKIP LOCKED.

Запускает настоящий Postgres через testcontainers и проверяет, что
при одновременном `claim_new_reviews` из двух сессий пачки не пересекаются.

Skip, если в системе нет Docker/testcontainers.
"""

from __future__ import annotations

import asyncio

import pytest

testcontainers = pytest.importorskip("testcontainers.postgres")
asyncpg = pytest.importorskip("asyncpg")  # noqa: F841

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

try:
    from testcontainers.postgres import PostgresContainer
except Exception:  # pragma: no cover
    pytest.skip("testcontainers.postgres недоступен", allow_module_level=True)


@pytest.fixture(scope="module")
def postgres_url() -> str:
    """Поднимает Postgres 16 в контейнере, отдаёт asyncpg-URL."""
    try:
        container = PostgresContainer("postgres:16-alpine")
        container.start()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Docker недоступен: {exc}")

    try:
        sync_url = container.get_connection_url()
        async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        yield async_url
    finally:
        container.stop()


@pytest.fixture
async def session_factory(postgres_url: str):
    from app.db.base import Base  # noqa: PLC0415
    from app.models.review import Review  # noqa: F401, PLC0415

    engine = create_async_engine(postgres_url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield maker
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_claim_is_atomic_under_concurrency(session_factory):
    from app.models.review import Review, ReviewStatus  # noqa: PLC0415
    from app.services.reviews import claim_new_reviews  # noqa: PLC0415

    async with session_factory() as seed:
        for i in range(20):
            seed.add(Review(name=f"user-{i}", text=f"review text {i}", status=ReviewStatus.NEW))
        await seed.commit()

    async def claim(limit: int) -> list[int]:
        async with session_factory() as s:
            items = await claim_new_reviews(s, limit=limit)
            return [r.id for r in items]

    a, b = await asyncio.gather(claim(10), claim(10))

    assert set(a).isdisjoint(set(b)), f"пересечение пачек: {set(a) & set(b)}"
    assert len(a) + len(b) == 20

    async with session_factory() as s:
        rows = (await s.execute(text("SELECT COUNT(*) FROM reviews WHERE status='processing'"))).scalar()
        assert rows == 20


@pytest.mark.asyncio
async def test_claim_returns_empty_when_no_new(session_factory):
    from app.services.reviews import claim_new_reviews  # noqa: PLC0415

    async with session_factory() as s:
        items = await claim_new_reviews(s, limit=5)
        assert items == []
