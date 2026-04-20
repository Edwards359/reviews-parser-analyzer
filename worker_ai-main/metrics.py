"""Prometheus-метрики воркера.

Экспонируются на `/metrics` (тот же процесс, что и webhook_server).
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

REGISTRY = CollectorRegistry(auto_describe=True)

reviews_processed_total = Counter(
    "worker_reviews_processed_total",
    "Количество обработанных воркером отзывов",
    ["tone"],  # positive | negative | neutral | ai | failed
    registry=REGISTRY,
)

reviews_failed_total = Counter(
    "worker_reviews_failed_total",
    "Количество отзывов, которые воркер не смог обработать",
    registry=REGISTRY,
)

llm_requests_total = Counter(
    "worker_llm_requests_total",
    "Вызовы LLM-провайдера",
    ["provider", "outcome"],  # outcome: ok | error | fallback
    registry=REGISTRY,
)

llm_latency_seconds = Histogram(
    "worker_llm_latency_seconds",
    "Время вызова LLM-провайдера",
    ["provider"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

telegram_notifications_total = Counter(
    "worker_telegram_notifications_total",
    "Уведомления в Telegram",
    ["outcome"],  # sent | skipped | failed
    registry=REGISTRY,
)

state_entries_gauge = Gauge(
    "worker_state_entries",
    "Текущее число записей в state.json (уведомлённые review_id).",
    registry=REGISTRY,
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
