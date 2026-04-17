from functools import lru_cache

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

UNSAFE_TOKENS = {"change-me", "changeme", "", "secret", "token"}


class Settings(BaseSettings):
    postgres_db: str = "reviews_db"
    postgres_user: str = "reviews_user"
    postgres_password: str = "reviews_password"
    postgres_host: str = "db"
    postgres_port: int = 5432
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    worker_api_token: str = "change-me"
    allow_insecure_token: bool = False
    webhook_target_url: str = ""
    webhook_timeout_seconds: float = 5.0
    public_rate_limit_per_minute: int = 30
    environment: str = "local"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("worker_api_token")
    @classmethod
    def _strip_token(cls, value: str) -> str:
        return value.strip()

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def token_is_safe(self) -> bool:
        token = self.worker_api_token.lower()
        return token not in UNSAFE_TOKENS and len(token) >= 16


@lru_cache
def get_settings() -> Settings:
    return Settings()
