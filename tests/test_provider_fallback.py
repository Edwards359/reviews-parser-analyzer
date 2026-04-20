"""Интеграционный тест: при сбое основного LLM-провайдера
processor.analyze_review возвращает осмысленный ответ через fallback
(эвристику по словарю + шаблон ответа).
"""

from __future__ import annotations

import pytest
from models import AnalysisResult, ReviewTone
from providers.base import LLMProvider
from providers.fallback import FallbackProvider
from providers.registry import get_provider


class _BoomProvider:
    name = "boom"

    async def analyze(self, review_text: str) -> AnalysisResult:  # noqa: ARG002
        raise RuntimeError("LLM is down")


@pytest.mark.asyncio
async def test_analyze_falls_back_on_provider_error(monkeypatch: pytest.MonkeyPatch):
    import processor

    monkeypatch.setattr(processor, "_provider", _BoomProvider())

    result = await processor.analyze_review("Ужасно, товар сломался сразу")

    assert isinstance(result, AnalysisResult)
    assert result.tone == ReviewTone.NEGATIVE
    assert result.reply
    assert len(result.reply) >= 5


@pytest.mark.asyncio
async def test_analyze_positive_review_via_fallback(monkeypatch: pytest.MonkeyPatch):
    import processor

    monkeypatch.setattr(processor, "_provider", _BoomProvider())

    result = await processor.analyze_review("Всё супер, спасибо огромное!")

    assert result.tone == ReviewTone.POSITIVE
    assert result.reply


def test_registry_returns_fallback_when_no_keys(monkeypatch: pytest.MonkeyPatch):
    """Без ключей реестр провайдеров не должен падать — возвращает FallbackProvider."""
    from config import get_settings

    get_settings.cache_clear()
    for env in ("OPENAI_API_KEY", "GIGACHAT_CREDENTIALS", "YANDEX_API_KEY", "YANDEX_FOLDER_ID"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    provider: LLMProvider = get_provider()
    assert isinstance(provider, FallbackProvider)
    assert provider.name == "fallback"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_fallback_provider_produces_valid_analysis():
    provider = FallbackProvider()
    result = await provider.analyze("Очень понравилось, рекомендую!")

    assert isinstance(result, AnalysisResult)
    assert result.tone in (ReviewTone.POSITIVE, ReviewTone.NEGATIVE, ReviewTone.NEUTRAL)
    assert result.reply
