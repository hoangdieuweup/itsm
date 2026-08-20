"""Settings owned by the storage integration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageConfig(BaseSettings):
    """Environment driven settings for object storage."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="STORAGE__", extra="ignore")

    ENDPOINT: str = ""
    BUCKET: str = ""
    ACCESS_KEY: str = ""
    SECRET_KEY: str = ""
    REGION: str = "us-east-1"


storage_settings = StorageConfig()
