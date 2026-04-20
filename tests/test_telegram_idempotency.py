"""Интеграционный тест: Telegram-уведомления идемпотентны.

Проверяем связку state.json + send_new_review_notification:
второй вызов для того же review_id не должен ходить в HTTP.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import state as state_module
import telegram_bot
from models import RemoteReview, ReviewStatus


def _make_review(rid: int) -> RemoteReview:
    return RemoteReview(
        id=rid,
        parent_id=None,
        name="Тестер",
        text="Отличный сервис, спасибо!",
        status=ReviewStatus.NEW,
        tone="positive",
        language=None,
        is_ai=False,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


class _FakeAsyncClient:
    """Минимальный httpx.AsyncClient, считающий POST-вызовы."""

    counter: dict[str, int] = {"posts": 0}

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, url: str, *, json: dict) -> httpx.Response:  # noqa: A002
        _FakeAsyncClient.counter["posts"] += 1
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"ok": True, "result": {"message_id": 1}})


@pytest.fixture
def telegram_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Подменяем настройки Telegram, state-файл и httpx.AsyncClient."""
    from config import Settings, get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_USER_CHAT_ID", "123456")
    monkeypatch.setenv("STATE_FILE_PATH", str(tmp_path / "state.json"))

    fresh = Settings()
    monkeypatch.setattr(telegram_bot, "settings", fresh)
    monkeypatch.setattr(state_module, "get_settings", lambda: fresh)

    _FakeAsyncClient.counter["posts"] = 0
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    yield fresh

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_telegram_notification_is_sent_once(telegram_env, tmp_path: Path):
    worker_state = state_module.get_worker_state()
    review = _make_review(rid=42)

    assert worker_state.is_notified(review.id) is False

    sent_first = await telegram_bot.send_new_review_notification(review)
    assert sent_first is True
    assert _FakeAsyncClient.counter["posts"] == 1

    worker_state.mark_notified(review.id)
    assert worker_state.is_notified(review.id) is True

    if not worker_state.is_notified(review.id):  # pragma: no cover - гварнулись
        await telegram_bot.send_new_review_notification(review)

    assert _FakeAsyncClient.counter["posts"] == 1


@pytest.mark.asyncio
async def test_state_persists_across_instances(tmp_path: Path, telegram_env):
    path = str(tmp_path / "state.json")
    s1 = state_module.WorkerState(path)
    s1.mark_notified(7)
    s1.mark_notified(8)

    s2 = state_module.WorkerState(path)
    assert s2.is_notified(7) is True
    assert s2.is_notified(8) is True
    assert s2.is_notified(9) is False
