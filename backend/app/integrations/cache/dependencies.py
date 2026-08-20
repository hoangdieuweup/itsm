"""Dependency wiring for the cache integration."""

from fastapi import Request

from app.integrations.cache.client import CacheClient
from app.integrations.cache.config import cache_settings


async def get_cache(request: Request) -> CacheClient:
    """Provide the cache client backed by the process wide pool."""
    return CacheClient(request.app.state.redis, cache_settings.DEFAULT_TTL)
