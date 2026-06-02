"""Application configuration via Pydantic settings."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "margin-backend"
    app_env: Literal["local", "dev", "staging", "production"] = "local"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"
    app_secret_key: str = Field(..., min_length=16)
    app_timezone: str = "Europe/Moscow"

    # JWT
    jwt_secret_key: str = Field(..., min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "margin"
    postgres_user: str = "margin"
    postgres_password: str = "margin"
    database_url: str | None = None

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: str | None = None

    # Celery
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # iikoCloud
    iiko_api_base_url: str = "https://api-ru.iiko.services/api/1"
    iiko_token_ttl_seconds: int = 3300
    iiko_http_timeout: int = 30
    iiko_retry_attempts: int = 4

    # CORS
    cors_origins: list[str] = Field(default_factory=list)

    # Telegram (optional)
    telegram_bot_token: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_uri(self) -> str:
        """Sync URI for Alembic / Celery."""
        uri = self.sqlalchemy_database_uri
        return uri.replace("+asyncpg", "+psycopg2")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_uri(self) -> str:
        if self.redis_url:
            return self.redis_url
        return str(
            RedisDsn.build(
                scheme="redis",
                host=self.redis_host,
                port=self.redis_port,
                path=str(self.redis_db),
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_uri

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_uri


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
