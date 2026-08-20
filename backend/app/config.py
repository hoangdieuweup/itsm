"""Global settings. Module specific settings live in that module's config.py."""

from pydantic import PostgresDsn
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

    DOCS_USERNAME: str | None = None
    DOCS_PASSWORD: str | None = None


settings = Config()
