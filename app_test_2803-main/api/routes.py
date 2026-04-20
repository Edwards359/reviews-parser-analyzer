from __future__ import annotations

import asyncio
import csv
import io
import logging
from pathlib import Path

from app.config import Settings, get_settings
from app.db.session import get_db_session, get_engine
from app.models.review import Review, ReviewStatus
from app.schemas import (
    AIReplyCreate,
    ClaimResponse,
    ReviewCreate,
    ReviewListResponse,
    ReviewRead,
    ReviewUpdate,
)
from app.services.metrics import (
    render_metrics,
    reviews_claimed_total,
    reviews_created_total,
    reviews_retry_total,
    reviews_status_gauge,
)
from app.services.ratelimit import SlidingWindowRateLimiter
from app.services.reviews import (
    claim_new_reviews,
    compute_text_hash,
    find_recent_duplicate,
    notify_webhook,
    reset_review_for_retry,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()
_settings = get_settings()
_rate_limiter = SlidingWindowRateLimiter(max_requests=_settings.public_rate_limit_per_minute)


def require_worker_token(
    x_worker_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.worker_api_token
    if not expected or not x_worker_token or x_worker_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid worker token.")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(request: Request) -> None:
    if not _rate_limiter.allow(_client_ip(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try later.",
        )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/healthz", tags=["health"], summary="Liveness-probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", tags=["health"], summary="Readiness-probe (БД)")
async def readyz() -> dict[str, str]:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(select(1))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not ready: {exc}",
        ) from exc
    return {"status": "ready"}


@router.get("/metrics", include_in_schema=False)
async def metrics(session: AsyncSession = Depends(get_db_session)) -> Response:
    """Prometheus-эндпоинт. Перед выгрузкой обновляет gauge по статусам отзывов."""
    try:
        result = await session.execute(
            select(Review.status, func.count(Review.id)).group_by(Review.status)
        )
        counts = {row[0].value if hasattr(row[0], "value") else str(row[0]): int(row[1]) for row in result}
        for st in ReviewStatus:
            reviews_status_gauge.labels(status=st.value).set(counts.get(st.value, 0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to refresh status gauge: %s", exc)

    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


# --------- v1 API ---------
api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get(
    "/reviews",
    response_model=ReviewListResponse,
    tags=["public"],
    summary="Список отзывов с фильтрами и пагинацией",
)
async def list_reviews_v1(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: ReviewStatus | None = Query(default=None, alias="status"),
    tone: str | None = Query(default=None),
    is_ai: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ReviewListResponse:
    conditions = []
    if status_filter is not None:
        conditions.append(Review.status == status_filter)
    if tone is not None:
        conditions.append(Review.tone == tone)
    if is_ai is not None:
        conditions.append(Review.is_ai.is_(is_ai))

    base = select(Review)
    count = select(func.count(Review.id))
    for condition in conditions:
        base = base.where(condition)
        count = count.where(condition)

    base = base.order_by(Review.created_at.desc(), Review.id.desc()).limit(limit).offset(offset)
    items = list((await session.execute(base)).scalars().all())
    total = int((await session.execute(count)).scalar_one() or 0)
    return ReviewListResponse(
        items=[ReviewRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@api_v1.post(
    "/reviews",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    tags=["public"],
    summary="Создание отзыва (с rate-limit и дедупликацией по тексту)",
)
async def create_review_v1(
    payload: ReviewCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Review:
    _enforce_rate_limit(request)

    if payload.parent_id is not None:
        parent_review = await session.get(Review, payload.parent_id)
        if parent_review is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent review not found.")

    text_hash = compute_text_hash(payload.text)
    duplicate = await find_recent_duplicate(session, text_hash, payload.parent_id)
    if duplicate is not None:
        return duplicate

    review = Review(
        parent_id=payload.parent_id,
        name=payload.name,
        text=payload.text,
        text_hash=text_hash,
        status=ReviewStatus.NEW,
        is_ai=False,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)

    reviews_created_total.labels(source="public").inc()
    asyncio.create_task(notify_webhook(settings, review))
    return review


@api_v1.post(
    "/reviews/ai-reply",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_worker_token)],
    tags=["worker"],
    summary="Публикация ответа от AI (is_ai=true ставит сервер)",
)
async def create_ai_reply_v1(
    payload: AIReplyCreate,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Review:
    parent_review = await session.get(Review, payload.parent_id)
    if parent_review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent review not found.")

    author_name = (payload.name or "").strip() or "AI Support"
    review = Review(
        parent_id=payload.parent_id,
        name=author_name,
        text=payload.text,
        text_hash=compute_text_hash(payload.text),
        status=ReviewStatus.PROCESSED,
        is_ai=True,
        tone=None,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    reviews_created_total.labels(source="ai").inc()
    return review


@api_v1.post(
    "/reviews/claim",
    response_model=ClaimResponse,
    dependencies=[Depends(require_worker_token)],
    tags=["worker"],
    summary="Атомарный claim (FOR UPDATE SKIP LOCKED)",
    description=(
        "Возвращает до `limit` отзывов со статусом `new`, переводя их в `processing`. "
        "Несколько воркеров могут вызывать параллельно — пачки не пересекаются."
    ),
)
async def claim_reviews_v1(
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimResponse:
    claimed = await claim_new_reviews(session, limit=limit)
    if claimed:
        reviews_claimed_total.inc(len(claimed))
    return ClaimResponse(items=[ReviewRead.model_validate(item) for item in claimed])


@api_v1.patch(
    "/reviews/{review_id}",
    response_model=ReviewRead,
    dependencies=[Depends(require_worker_token)],
    tags=["worker"],
    summary="Обновление отзыва воркером (status/tone/response/last_error)",
)
async def update_review_v1(
    review_id: int,
    payload: ReviewUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> Review:
    review = await session.get(Review, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")

    if payload.status is not None:
        review.status = payload.status
        if payload.status == ReviewStatus.PROCESSED:
            review.processed_at = func.now()
    if payload.response is not None:
        review.response = payload.response
    if payload.tone is not None:
        review.tone = payload.tone.value
    if payload.last_error is not None:
        review.last_error = payload.last_error

    await session.commit()
    await session.refresh(review)
    return review


@api_v1.post(
    "/reviews/{review_id}/retry",
    response_model=ReviewRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_worker_token)],
    tags=["worker"],
    summary="Повторная постановка failed-отзыва в очередь",
    description=(
        "Возвращает отзыв из `failed`/`processing` обратно в статус `new` "
        "и увеличивает `retry_count`. После достижения лимита отвечает 409. "
        "На `processed`/`new` отвечает 409. На AI-ответах — 409."
    ),
)
async def retry_review_v1(
    review_id: int,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Review:
    try:
        review = await reset_review_for_retry(
            session, review_id, max_retries=settings.max_retry_count
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
    reviews_retry_total.inc()
    asyncio.create_task(notify_webhook(settings, review))
    return review


@api_v1.get(
    "/reviews.csv",
    tags=["public"],
    summary="Экспорт всех отзывов в CSV",
    response_class=StreamingResponse,
)
async def export_reviews_csv_v1(
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    result = await session.execute(select(Review).order_by(Review.id.asc()))
    rows = result.scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "parent_id", "name", "is_ai", "status", "tone", "language", "created_at", "text", "response"]
    )
    for review in rows:
        writer.writerow(
            [
                review.id,
                review.parent_id or "",
                review.name or "",
                int(bool(review.is_ai)),
                review.status.value if hasattr(review.status, "value") else str(review.status),
                review.tone or "",
                review.language or "",
                review.created_at.isoformat() if review.created_at else "",
                (review.text or "").replace("\n", " "),
                (review.response or "").replace("\n", " "),
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reviews.csv"},
    )


# --------- Legacy aliases (обратная совместимость) ---------


@router.get("/api/reviews", response_model=list[ReviewRead], tags=["legacy"])
async def list_reviews_legacy(
    session: AsyncSession = Depends(get_db_session),
) -> list[Review]:
    result = await session.execute(
        select(Review).order_by(Review.created_at.desc(), Review.id.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/api/reviews",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    tags=["legacy"],
)
async def create_review_legacy(
    payload: ReviewCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Review:
    return await create_review_v1(payload=payload, request=request, session=session, settings=settings)


@router.patch("/api/reviews/{review_id}", response_model=ReviewRead, tags=["legacy"])
async def update_review_legacy(
    review_id: int,
    payload: ReviewUpdate,
    session: AsyncSession = Depends(get_db_session),
    x_worker_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Review:
    if not settings.worker_api_token or x_worker_token != settings.worker_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid worker token.")
    return await update_review_v1(review_id=review_id, payload=payload, session=session)


router.include_router(api_v1)
