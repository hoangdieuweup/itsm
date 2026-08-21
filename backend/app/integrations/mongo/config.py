"""Settings owned by the mongo integration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MongoConfig(BaseSettings):
    """Environment driven settings for MongoDB."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MONGO__", extra="ignore")

    URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "itsm"
    SERVER_SELECTION_TIMEOUT_MS: int = 2000


mongo_settings = MongoConfig()
