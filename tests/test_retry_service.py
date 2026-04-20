"""Юнит-тесты сервиса reset_review_for_retry (без Postgres, in-memory SQLite)."""

from __future__ import annotations

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


@pytest.fixture
async def sqlite_session():
    from app.db.base import Base  # noqa: PLC0415

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_retry_moves_failed_back_to_new(sqlite_session):
    from app.models.review import Review, ReviewStatus  # noqa: PLC0415
    from app.services.reviews import reset_review_for_retry  # noqa: PLC0415

    sqlite_session.add(
        Review(name="x", text="t", status=ReviewStatus.FAILED, retry_count=0, last_error="oops")
    )
    await sqlite_session.commit()

    refreshed = await reset_review_for_retry(sqlite_session, 1, max_retries=5)
    assert refreshed is not None
    assert refreshed.status == ReviewStatus.NEW
    assert refreshed.retry_count == 1


@pytest.mark.asyncio
async def test_retry_respects_max_retries(sqlite_session):
    from app.models.review import Review, ReviewStatus  # noqa: PLC0415
    from app.services.reviews import reset_review_for_retry  # noqa: PLC0415

    sqlite_session.add(
        Review(name="x", text="t", status=ReviewStatus.FAILED, retry_count=5)
    )
    await sqlite_session.commit()

    with pytest.raises(ValueError, match="лимит retry"):
        await reset_review_for_retry(sqlite_session, 1, max_retries=5)


@pytest.mark.asyncio
async def test_retry_rejects_processed(sqlite_session):
    from app.models.review import Review, ReviewStatus  # noqa: PLC0415
    from app.services.reviews import reset_review_for_retry  # noqa: PLC0415

    sqlite_session.add(Review(name="x", text="t", status=ReviewStatus.PROCESSED))
    await sqlite_session.commit()

    with pytest.raises(ValueError, match="Нельзя перезапустить"):
        await reset_review_for_retry(sqlite_session, 1)


@pytest.mark.asyncio
async def test_retry_returns_none_for_missing(sqlite_session):
    from app.services.reviews import reset_review_for_retry  # noqa: PLC0415

    result = await reset_review_for_retry(sqlite_session, 999)
    assert result is None


@pytest.mark.asyncio
async def test_retry_rejects_ai_reply(sqlite_session):
    from app.models.review import Review, ReviewStatus  # noqa: PLC0415
    from app.services.reviews import reset_review_for_retry  # noqa: PLC0415

    sqlite_session.add(
        Review(name="AI", text="t", is_ai=True, status=ReviewStatus.PROCESSED)
    )
    await sqlite_session.commit()

    with pytest.raises(ValueError, match="AI"):
        await reset_review_for_retry(sqlite_session, 1)
