"""Redis client with entity versioning and stampede protection."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from app.core.base.markers import helper, integration
from app.integrations.cache.config import cache_settings
from app.integrations.cache.constants import CacheDefaults
from app.integrations.cache.exceptions import CacheUnavailable
from app.integrations.cache.keys import CacheKeyBuilder

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class RedisConnectionFactory:
    """Builds the process wide Redis client. Called once, from lifespan.py."""

    @staticmethod
    @integration
    def create() -> Redis:
        """Build a Redis client backed by a connection pool sized from settings."""
        pool = ConnectionPool.from_url(
            str(cache_settings.URL),
            decode_responses=True,
            max_connections=cache_settings.MAX_CONNECTIONS,
            socket_timeout=cache_settings.SOCKET_TIMEOUT,
        )
        return Redis(connection_pool=pool)


class CacheClient:
    """Cache aside client where invalidation bumps a generation counter."""

    def __init__(self, redis: Redis, default_ttl: int) -> None:
        self._redis = redis
        self._default_ttl = default_ttl
        self._inflight: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    @integration
    async def get_or_load(
        self,
        entity: str,
        entity_id: int,
        model: type[T],
        loader: Callable[[], Awaitable[T | None]],
        ttl: int | None = None,
    ) -> T | None:
        """Read from cache, otherwise load once and store the result."""
        try:
            version = await self._version(entity, entity_id)
            key = CacheKeyBuilder.entity_key(entity, entity_id, version)
            raw = await self._redis.get(key)
        except RedisError:
            logger.warning("cache unavailable, degrading to database", exc_info=True)
            return await loader()

        if raw is not None:
            try:
                return model.model_validate_json(raw)
            except ValidationError:
                logger.warning("stale payload schema key=%s", key)

        value = await self._single_flight(key, loader)
        if value is not None:
            try:
                await self._redis.set(key, value.model_dump_json(), ex=ttl or self._default_ttl)
            except RedisError:
                logger.warning("cache write failed key=%s", key, exc_info=True)
        return value

    @integration
    async def bump_version(self, entity: str, entity_id: int) -> None:
        """Invalidate every cached key of this entity in constant time."""
        try:
            key = CacheKeyBuilder.version_key(entity, entity_id)
            version = await self._redis.incr(key)
            await self._redis.expire(key, CacheDefaults.VERSION_TTL_SECONDS)
            logger.info("cache invalidated entity=%s id=%s version=%s", entity, entity_id, version)
        except RedisError:
            logger.error("invalidation failed entity=%s id=%s", entity, entity_id, exc_info=True)

    @integration
    async def set_json(self, key: str, value: dict, *, ttl: int) -> None:
        """Store a single-use or short-lived JSON value (not a versioned entity).

        Raises CacheUnavailable instead of degrading, unlike get_or_load: a
        PKCE state or an upstream token cache has no database to fall back
        to, so a caller that cannot tolerate a missing Redis must know
        immediately rather than silently losing the value.
        """
        try:
            await self._redis.set(key, json.dumps(value), ex=ttl)
        except RedisError as exc:
            logger.error("cache write failed key=%s", key, exc_info=True)
            raise CacheUnavailable() from exc

    @integration
    async def get_json(self, key: str) -> dict | None:
        """Read a value written by set_json, or None if missing or unreadable."""
        try:
            raw = await self._redis.get(key)
        except RedisError as exc:
            logger.error("cache read failed key=%s", key, exc_info=True)
            raise CacheUnavailable() from exc
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            logger.warning("undecodable payload key=%s", key)
            return None

    @integration
    async def delete(self, key: str) -> None:
        """Remove a key written by set_json. A no-op if it never existed."""
        try:
            await self._redis.delete(key)
        except RedisError:
            logger.warning("cache delete failed key=%s", key, exc_info=True)

    @integration
    async def try_acquire_lock(self, key: str, *, ttl: int) -> bool:
        """Attempt to take a distributed mutex. True if this caller now holds it."""
        try:
            return bool(await self._redis.set(key, "1", ex=ttl, nx=True))
        except RedisError as exc:
            logger.error("lock acquire failed key=%s", key, exc_info=True)
            raise CacheUnavailable() from exc

    @integration
    async def release_lock(self, key: str) -> None:
        """Release a mutex acquired by try_acquire_lock."""
        try:
            await self._redis.delete(key)
        except RedisError:
            logger.warning("lock release failed key=%s", key, exc_info=True)

    @helper
    async def _version(self, entity: str, entity_id: int) -> int:
        """Return the current generation of an entity, defaulting to one. Supports get_or_load above."""
        raw = await self._redis.get(CacheKeyBuilder.version_key(entity, entity_id))
        return int(raw) if raw else 1

    @helper
    async def _single_flight(self, key: str, loader: Callable[[], Awaitable[T | None]]) -> T | None:
        """Collapse concurrent misses on the same key into one loader call."""
        async with self._lock:
            future = self._inflight.get(key)
            if future is not None:
                return await asyncio.shield(future)
            future = asyncio.get_running_loop().create_future()
            self._inflight[key] = future

        try:
            value = await loader()
        except Exception as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(value)
            return value
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
