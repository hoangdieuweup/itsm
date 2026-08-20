"""Idempotent delivery for queue consumer handlers.

See references/messaging.md#idempotent-consumers. A handler wrapped with
idempotent(store) runs at most once per event_id, regardless of how many
times the broker redelivers the same message — required because AMQP only
guarantees at-least-once delivery, never exactly-once.
"""

import functools
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from redis.asyncio import Redis

from app.core.base.markers import integration

logger = logging.getLogger(__name__)

ConsumerHandler = Callable[[bytes], Awaitable[None]]


class IdempotencyStore(Protocol):
    """Contract a backing store for processed event ids must satisfy."""

    async def exists(self, key: str) -> bool:
        """Return whether this key has already been marked processed."""
        ...

    async def mark(self, key: str) -> None:
        """Record this key as processed."""
        ...


class idempotent:  # noqa: N801 -- lowercase by design, read as an annotation like @staticmethod
    """Skip a handler call if this message's event_id was already processed.

    The message body must be the JSON a DomainEvent serializes to (event_id
    at the top level) — every event published via Broker.publish already has
    one. A message with no event_id always runs; there is nothing to dedupe
    against.
    """

    def __init__(self, store: IdempotencyStore) -> None:
        self._store = store

    def __call__(self, handler: ConsumerHandler) -> ConsumerHandler:
        @functools.wraps(handler)
        async def wrapped(body: bytes) -> None:
            event_id = json.loads(body).get("event_id")
            if event_id and await self._store.exists(event_id):
                logger.info("skipping already-processed event_id=%s", event_id)
                return
            await handler(body)
            if event_id:
                await self._store.mark(event_id)

        return wrapped


class RedisIdempotencyStore:
    """IdempotencyStore backed by Redis — a TTL'd key per event_id, cheap and self-expiring."""

    def __init__(self, redis: Redis, ttl_seconds: int = 86400) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    @integration
    async def exists(self, key: str) -> bool:
        """Return whether this key has already been marked processed."""
        return bool(await self._redis.exists(f"idempotent:{key}"))

    @integration
    async def mark(self, key: str) -> None:
        """Record this key as processed, expiring after ttl_seconds."""
        await self._redis.set(f"idempotent:{key}", "1", ex=self._ttl_seconds)
