from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")

CORRELATION_HEADER = "X-Request-ID"


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Единая настройка логов воркера с поддержкой correlation-id.

    Формат совпадает с веб-приложением, чтобы по cid можно было
    связать цепочку событий от POST /api/v1/reviews до ответа LLM.
    """
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


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:12]
