"""Prometheus-метрики веб-приложения.

Экспортируется бэк-end-friendly endpoint `/metrics` (plaintext, 0.0.4).
Метрики покрывают:
- HTTP-слой (кол-во запросов и latency по method+path+status)
- бизнес-события (создание отзывов, ai-replies, claim-пачки)
- состояние БД (счётчики по status)
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

REGISTRY = CollectorRegistry(auto_describe=True)

http_requests_total = Counter(
    "reviews_http_requests_total",
    "Количество HTTP-запросов к веб-приложению",
    ["method", "path", "status"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "reviews_http_request_duration_seconds",
    "Latency HTTP-запросов в секундах",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

reviews_created_total = Counter(
    "reviews_created_total",
    "Количество созданных отзывов (по происхождению)",
    ["source"],  # "public" | "ai"
    registry=REGISTRY,
)

reviews_claimed_total = Counter(
    "reviews_claimed_total",
    "Количество отзывов, забранных воркером через /claim",
    registry=REGISTRY,
)

reviews_status_gauge = Gauge(
    "reviews_status_current",
    "Текущее число отзывов в каждом статусе",
    ["status"],
    registry=REGISTRY,
)

reviews_retry_total = Counter(
    "reviews_retry_total",
    "Количество повторных постановок отзыва в очередь",
    registry=REGISTRY,
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
