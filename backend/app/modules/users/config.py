"""Settings owned by the users module."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class UsersConfig(BaseSettings):
    """Environment driven settings for the users module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="USERS__", extra="ignore")

    ADMIN_EMAIL: str | None = None


users_settings = UsersConfig()
