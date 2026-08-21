"""Global settings. Module specific settings live in that module's config.py."""

import json
from typing import Any

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import Environment, LogLevel


class Config(BaseSettings):
    """Settings that genuinely belong to the whole process."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "itsm"
    ENV: Environment = Environment.PRODUCTION
    LOG_LEVEL: LogLevel = LogLevel.INFO

    DATABASE_URL: PostgresDsn
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_STATEMENT_TIMEOUT_MS: int = 30000

    CORS_ORIGINS: list[str] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    BACKEND_BASE_URL: str = "http://localhost:8000"
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    DOCS_USERNAME: str | None = None
    DOCS_PASSWORD: str | None = None


settings = Config()
