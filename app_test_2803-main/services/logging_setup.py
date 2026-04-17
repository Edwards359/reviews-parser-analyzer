from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

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
