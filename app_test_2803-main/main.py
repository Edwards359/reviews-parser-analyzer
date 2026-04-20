from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from app.api.routes import router
from app.config import get_settings
from app.db.session import get_engine
from app.models import Review  # noqa: F401
from app.services.logging_setup import (
    CorrelationIdMiddleware,
    PrometheusMetricsMiddleware,
    setup_logging,
)
from fastapi import FastAPI

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if not settings.token_is_safe and not settings.allow_insecure_token:
        raise RuntimeError(
            "WORKER_API_TOKEN is missing or unsafe. Set a random value (>=16 chars) "
            "or enable ALLOW_INSECURE_TOKEN=true for local-only runs."
        )

    engine = get_engine()
    try:
        async with engine.connect():
            logger.info(
                "Database connection established: %s",
                engine.url.render_as_string(hide_password=True),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database is not reachable yet: %s", exc)

    yield


app = FastAPI(
    title="Reviews App",
    version="1.1.0",
    lifespan=lifespan,
    description=(
        "Хранилище клиентских отзывов + интеграция с LLM-воркером. "
        "Публичный API (`/api/reviews`, `/api/v1/reviews`) и служебный API "
        "воркера (`/api/v1/reviews/claim`, `/ai-reply`, `/retry`, `/{id}`)."
    ),
    openapi_tags=[
        {"name": "public", "description": "Публичные ручки: создание и чтение отзывов."},
        {"name": "worker", "description": "Служебные ручки воркера (X-Worker-Token)."},
        {"name": "health", "description": "Health/readiness/metrics."},
        {"name": "legacy", "description": "Старые алиасы для обратной совместимости."},
    ],
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(PrometheusMetricsMiddleware)
app.include_router(router)
