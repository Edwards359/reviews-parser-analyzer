from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["openai", "gigachat", "yandex", "fallback"]


class Settings(BaseSettings):
    target_site_url: str = "http://127.0.0.1:8000"
    worker_api_token: str = "change-me"
    worker_poll_interval: int = 10
    state_file_path: str = "data/state.json"
    state_max_entries: int = 10000
    state_max_age_days: int = 30
    ai_author_name: str = "AI Support"

    llm_provider: LLMProviderName = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini-2026-03-17"

    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"

    yandex_api_key: str = ""
    yandex_folder_id: str = ""
    yandex_model: str = "yandexgpt-lite"

    telegram_bot_token: str = ""
    telegram_user_chat_id: str = ""
    telegram_chat_id: str = Field(default="", deprecated=True)

    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8100
    enable_webhook: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
