from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from app.api.routes import router
from app.config import get_settings
from app.db.session import get_engine
from app.models import Review  # noqa: F401
from app.services.logging_setup import CorrelationIdMiddleware, setup_logging
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


app = FastAPI(title="Reviews App", version="1.0.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)
app.include_router(router)
