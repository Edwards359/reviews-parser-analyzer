from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import uvicorn
from config import get_settings
from fastapi import FastAPI

if TYPE_CHECKING:
    from worker import ReviewWorker


logger = logging.getLogger("worker.webhook")


def build_app(worker: ReviewWorker) -> FastAPI:
    app = FastAPI(title="Worker Webhook", version="1.0.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhook/review-created")
    async def review_created(payload: dict) -> dict[str, str]:
        logger.info("Webhook triggered for review id=%s", payload.get("id"))
        worker.trigger()
        return {"status": "triggered"}

    return app


async def run_webhook_server(worker: ReviewWorker) -> None:
    settings = get_settings()
    app = build_app(worker)
    config = uvicorn.Config(
        app,
        host=settings.webhook_host,
        port=settings.webhook_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()
