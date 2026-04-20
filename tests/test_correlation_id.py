"""Проверяем сквозную передачу correlation-id во воркере:
клиент воркера кладёт cid в заголовок исходящего HTTP,
webhook_server умеет его принять.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient


class _CapturingAsyncClient:
    captured: list[dict[str, str]] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def __aenter__(self) -> _CapturingAsyncClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None, **_: Any
    ) -> httpx.Response:
        _CapturingAsyncClient.captured.append(dict(headers or {}))
        request = httpx.Request(method, url, headers=headers)
        return httpx.Response(200, request=request, json={"items": []})


@pytest.mark.asyncio
async def test_client_sends_correlation_id(monkeypatch: pytest.MonkeyPatch):
    import client as worker_client
    from logging_setup import CORRELATION_HEADER, correlation_id_ctx

    _CapturingAsyncClient.captured = []
    monkeypatch.setattr(worker_client.httpx, "AsyncClient", _CapturingAsyncClient)

    token = correlation_id_ctx.set("cid-abc123")
    try:
        c = worker_client.ReviewSiteClient()
        await c.claim_new_reviews(limit=5)
    finally:
        correlation_id_ctx.reset(token)

    assert _CapturingAsyncClient.captured, "клиент не сделал ни одного запроса"
    first = _CapturingAsyncClient.captured[0]
    assert first.get(CORRELATION_HEADER) == "cid-abc123"
    assert first.get("X-Worker-Token"), "должен проставляться токен воркера"


def test_webhook_server_triggers_worker_with_cid():
    from logging_setup import CORRELATION_HEADER
    from webhook_server import build_app

    class _FakeWorker:
        def __init__(self) -> None:
            self.calls: list[tuple[int | None, str | None]] = []

        def trigger(
            self,
            review_id: int | None = None,
            correlation_id: str | None = None,
        ) -> None:
            self.calls.append((review_id, correlation_id))

    worker = _FakeWorker()
    app = build_app(worker)  # type: ignore[arg-type]
    client = TestClient(app)

    response = client.post(
        "/webhook/review-created",
        json={"event": "review.created", "id": 99, "text": "hello"},
        headers={CORRELATION_HEADER: "cid-from-web"},
    )
    assert response.status_code == 200
    assert response.headers.get(CORRELATION_HEADER) == "cid-from-web"

    assert worker.calls == [(99, "cid-from-web")]


def test_webhook_generates_cid_when_missing():
    from logging_setup import CORRELATION_HEADER
    from webhook_server import build_app

    class _FakeWorker:
        def trigger(self, **_: Any) -> None:
            pass

    app = build_app(_FakeWorker())  # type: ignore[arg-type]
    client = TestClient(app)

    response = client.post(
        "/webhook/review-created",
        json={"id": 1, "text": "t"},
    )
    assert response.status_code == 200
    assert response.headers.get(CORRELATION_HEADER)
