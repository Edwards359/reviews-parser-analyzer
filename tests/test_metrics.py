"""Проверяем, что Prometheus-метрики:
- действительно инкрементятся из processor/telegram_bot,
- отдаются в формате text/plain.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest


@pytest.mark.asyncio
async def test_processor_increments_llm_metrics_on_success(monkeypatch: pytest.MonkeyPatch):
    import metrics
    import processor
    from models import AnalysisResult, ReviewTone

    class OkProvider:
        name = "fake-ok"

        async def analyze(self, text: str) -> AnalysisResult:  # noqa: ARG002
            return AnalysisResult(tone=ReviewTone.POSITIVE, reply="ok")

    monkeypatch.setattr(processor, "_provider", OkProvider())

    before = metrics.llm_requests_total.labels(provider="fake-ok", outcome="ok")._value.get()
    await processor.analyze_review("hello")
    after = metrics.llm_requests_total.labels(provider="fake-ok", outcome="ok")._value.get()

    assert after == before + 1


@pytest.mark.asyncio
async def test_processor_increments_llm_metrics_on_error(monkeypatch: pytest.MonkeyPatch):
    import metrics
    import processor

    class BoomProvider:
        name = "fake-boom"

        async def analyze(self, text: str) -> Any:  # noqa: ARG002
            raise RuntimeError("down")

    monkeypatch.setattr(processor, "_provider", BoomProvider())

    before_err = metrics.llm_requests_total.labels(
        provider="fake-boom", outcome="error"
    )._value.get()
    before_fb = metrics.llm_requests_total.labels(
        provider="fallback", outcome="fallback"
    )._value.get()

    await processor.analyze_review("совсем плохо")

    assert (
        metrics.llm_requests_total.labels(provider="fake-boom", outcome="error")._value.get()
        == before_err + 1
    )
    assert (
        metrics.llm_requests_total.labels(provider="fallback", outcome="fallback")._value.get()
        == before_fb + 1
    )


@pytest.mark.asyncio
async def test_telegram_metrics(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import metrics
    import telegram_bot
    from config import Settings, get_settings
    from models import RemoteReview, ReviewStatus

    get_settings.cache_clear()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tk")
    monkeypatch.setenv("TELEGRAM_USER_CHAT_ID", "42")
    monkeypatch.setattr(telegram_bot, "settings", Settings())

    class _OK:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url: str, *, json: dict) -> httpx.Response:
            request = httpx.Request("POST", url)
            return httpx.Response(200, request=request, json={"ok": True})

    monkeypatch.setattr(telegram_bot.httpx, "AsyncClient", _OK)

    before_sent = metrics.telegram_notifications_total.labels(outcome="sent")._value.get()

    review = RemoteReview(
        id=1,
        parent_id=None,
        name="a",
        text="t",
        status=ReviewStatus.NEW,
        tone="neutral",
        is_ai=False,
        created_at=__import__("datetime").datetime(2026, 1, 1),
    )
    ok = await telegram_bot.send_new_review_notification(review)
    assert ok is True

    assert (
        metrics.telegram_notifications_total.labels(outcome="sent")._value.get()
        == before_sent + 1
    )

    get_settings.cache_clear()


def test_webhook_server_exposes_metrics_endpoint():
    from fastapi.testclient import TestClient
    from webhook_server import build_app

    class _Fake:
        def trigger(self, **_: Any) -> None:
            pass

    app = build_app(_Fake())  # type: ignore[arg-type]
    client = TestClient(app)
    resp = client.get("/metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert b"worker_reviews_processed_total" in resp.content or b"# HELP" in resp.content
