from __future__ import annotations

import logging

from config import get_settings

from .base import LLMProvider
from .fallback import FallbackProvider

logger = logging.getLogger("worker.provider")


def get_provider() -> LLMProvider:
    settings = get_settings()
    name = settings.llm_provider.lower()

    try:
        if name == "openai":
            if not settings.openai_api_key:
                logger.info("OPENAI_API_KEY is empty, using fallback provider")
                return FallbackProvider()
            from .openai_provider import OpenAIProvider

            return OpenAIProvider()

        if name == "gigachat":
            if not settings.gigachat_credentials:
                logger.info("GIGACHAT_CREDENTIALS is empty, using fallback provider")
                return FallbackProvider()
            from .gigachat_provider import GigaChatProvider

            return GigaChatProvider()

        if name == "yandex":
            if not settings.yandex_api_key or not settings.yandex_folder_id:
                logger.info("Yandex credentials are empty, using fallback provider")
                return FallbackProvider()
            from .yandex_provider import YandexGPTProvider

            return YandexGPTProvider()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to initialize provider %s: %s", name, exc)

    return FallbackProvider()
