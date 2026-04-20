from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

import httpx
from app.config import Settings
from app.models.review import Review, ReviewStatus
from app.services.logging_setup import correlation_id_ctx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CORRELATION_HEADER = "X-Request-ID"


def compute_text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


async def find_recent_duplicate(
    session: AsyncSession,
    text_hash: str,
    parent_id: int | None,
    window_seconds: int = 600,
) -> Review | None:
    """Ищет дубликат того же текста (тот же parent) за последние N секунд."""
    stmt = (
        select(Review)
        .where(Review.text_hash == text_hash)
        .where(Review.parent_id.is_(parent_id) if parent_id is None else Review.parent_id == parent_id)
        .where(Review.created_at >= func.now() - func.make_interval(0, 0, 0, 0, 0, 0, window_seconds))
        .order_by(Review.created_at.desc())
        .limit(1)
    )
    try:
        result = await session.execute(stmt)
    except Exception:  # pragma: no cover - на не-Postgres просто пропускаем
        return None
    return result.scalar_one_or_none()


async def claim_new_reviews(session: AsyncSession, limit: int = 10) -> list[Review]:
    """Атомарно забирает до `limit` отзывов со статусом `new`, переводит в `processing`.

    Использует `FOR UPDATE SKIP LOCKED` в PostgreSQL — несколько worker'ов не конфликтуют.
    """
    select_stmt = (
        select(Review.id)
        .where(Review.status == ReviewStatus.NEW)
        .where(Review.is_ai.is_(False))
        .order_by(Review.created_at.asc(), Review.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    ids = (await session.execute(select_stmt)).scalars().all()
    if not ids:
        return []

    now = datetime.now(tz=UTC)
    update_stmt = (
        update(Review)
        .where(Review.id.in_(ids))
        .values(status=ReviewStatus.PROCESSING, claimed_at=now)
        .returning(Review)
    )
    result = await session.execute(update_stmt)
    claimed = list(result.scalars().all())
    await session.commit()
    return claimed


async def reset_review_for_retry(
    session: AsyncSession,
    review_id: int,
    max_retries: int = 5,
) -> Review | None:
    """Переводит отзыв из `failed`/`processing` обратно в `new` для повторной обработки.

    - `None` если отзыва не существует.
    - Бросает ValueError, если исчерпан лимит retry.
    - Бросает ValueError, если отзыв нельзя перезапустить (уже processed / is_ai).
    """
    review = await session.get(Review, review_id)
    if review is None:
        return None

    if review.is_ai:
        raise ValueError("AI-ответы не перезапускаются")

    if review.status in (ReviewStatus.NEW, ReviewStatus.PROCESSED):
        raise ValueError(f"Нельзя перезапустить отзыв в статусе {review.status.value!r}")

    if review.retry_count >= max_retries:
        raise ValueError(
            f"Превышен лимит retry ({review.retry_count}/{max_retries}) для отзыва {review_id}"
        )

    review.status = ReviewStatus.NEW
    review.retry_count = (review.retry_count or 0) + 1
    review.claimed_at = None
    await session.commit()
    await session.refresh(review)
    return review


async def notify_webhook(settings: Settings, review: Review) -> None:
    if not settings.webhook_target_url:
        return
    payload = {
        "event": "review.created",
        "id": review.id,
        "parent_id": review.parent_id,
        "name": review.name,
        "text": review.text,
    }
    headers: dict[str, str] = {}
    cid = correlation_id_ctx.get()
    if cid and cid != "-":
        headers[CORRELATION_HEADER] = cid
    try:
        async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
            await client.post(settings.webhook_target_url, json=payload, headers=headers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook delivery failed: %s", exc)
