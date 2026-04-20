from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import uvicorn
from config import get_settings
from fastapi import FastAPI, Request
from logging_setup import CORRELATION_HEADER, correlation_id_ctx, new_correlation_id
from metrics import render_metrics, state_entries_gauge
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

if TYPE_CHECKING:
    from worker import ReviewWorker


logger = logging.getLogger("worker.webhook")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Подхватываем X-Request-ID от веб-приложения (если пришёл),
    иначе генерируем свой. Одно и то же поле cid будет в логах веба и воркера.
    """

    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
        token = correlation_id_ctx.set(cid)
        try:
            response: Response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)
        response.headers[CORRELATION_HEADER] = cid
        return response


def build_app(worker: ReviewWorker) -> FastAPI:
    app = FastAPI(title="Worker Webhook", version="1.0.0")
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        try:
            state_entries_gauge.set(worker.state.size())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to refresh state gauge: %s", exc)
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    @app.post("/webhook/review-created")
    async def review_created(payload: dict, request: Request) -> dict[str, str]:
        review_id = payload.get("id")
        cid = request.headers.get(CORRELATION_HEADER) or correlation_id_ctx.get()
        logger.info("Webhook triggered for review id=%s", review_id)
        worker.trigger(
            review_id=review_id if isinstance(review_id, int) else None,
            correlation_id=cid if cid and cid != "-" else None,
        )
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
