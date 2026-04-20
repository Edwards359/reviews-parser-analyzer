from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar

from app.services.metrics import http_request_duration_seconds, http_requests_total
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | cid=%(correlation_id)s | %(message)s"
        )
    )
    handler.addFilter(CorrelationIdFilter())
    root.addHandler(handler)
    root.setLevel(level)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    header_name = "X-Request-ID"

    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get(self.header_name) or uuid.uuid4().hex[:12]
        token = correlation_id_ctx.set(cid)
        try:
            response: Response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)
        response.headers[self.header_name] = cid
        return response


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Считает HTTP-запросы и латентность. `path` берём из route-шаблона
    (например, `/api/v1/reviews/{review_id}`), чтобы не плодить лейблы.
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", None) or "__unmatched__"
            elapsed = time.perf_counter() - start
            http_requests_total.labels(
                method=request.method, path=path, status=str(status_code)
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method, path=path
            ).observe(elapsed)
        return response
