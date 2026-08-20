"""Settings owned by the cache integration."""

from pydantic import RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.cache.constants import CacheDefaults


class CacheConfig(BaseSettings):
    """Environment driven settings for Redis."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CACHE__", extra="ignore")

    URL: RedisDsn = "redis://localhost:6379/0"
    DEFAULT_TTL: int = CacheDefaults.DEFAULT_TTL_SECONDS
    SOCKET_TIMEOUT: float = 1.0
    MAX_CONNECTIONS: int = 50


cache_settings = CacheConfig()
