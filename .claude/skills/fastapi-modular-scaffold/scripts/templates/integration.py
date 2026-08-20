"""Templates for integration modules.

An integration is a module like any other: it owns its config, constants,
exceptions and client. It differs from a domain module only in what it lacks,
namely models.py and router.py, because it owns no tables and no HTTP surface.
"""

CACHE_FILES = ("constants", "config", "exceptions", "keys", "client", "dependencies")
QUEUE_FILES = ("constants", "config", "exceptions", "topology", "client", "dependencies")
STORAGE_FILES = ("constants", "config", "exceptions", "client", "dependencies")


def cache_constants() -> str:
    """Render integrations/cache/constants.py."""
    return '''
"""Constants owned by the cache integration."""

from enum import StrEnum


class CacheDefaults:
    """Numeric defaults owned by the cache integration."""

    VERSION_TTL_SECONDS = 86400
    DEFAULT_TTL_SECONDS = 300
    PAYLOAD_SCHEMA_VERSION = 1


class CacheErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UNAVAILABLE = "cache_unavailable"
    SERIALIZATION_FAILED = "cache_serialization_failed"
'''


def cache_config() -> str:
    """Render integrations/cache/config.py."""
    return '''
"""Settings owned by the cache integration."""

from pydantic import RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.cache.constants import CacheDefaults


class CacheConfig(BaseSettings):
    """Environment driven settings for Redis."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CACHE_", extra="ignore")

    URL: RedisDsn = "redis://localhost:6379/0"
    DEFAULT_TTL: int = CacheDefaults.DEFAULT_TTL_SECONDS
    SOCKET_TIMEOUT: float = 1.0
    MAX_CONNECTIONS: int = 50


cache_settings = CacheConfig()
'''


def cache_exceptions() -> str:
    """Render integrations/cache/exceptions.py."""
    return '''
"""Errors owned by the cache integration."""

from app.core.exceptions import IntegrationError
from app.integrations.cache.constants import CacheErrorCode


class CacheUnavailable(IntegrationError):
    """Raised when Redis cannot be reached and no fallback is possible."""

    code = CacheErrorCode.UNAVAILABLE
    message = "Cache backend unavailable"
'''


def cache_keys() -> str:
    """Render integrations/cache/keys.py."""
    return '''
"""Every cache key in the application is built here.

Keys assembled as f-strings scattered across modules make correct invalidation
impossible, because nothing can enumerate what exists. Each domain module
supplies its own entity name through its constants module.
"""

from app.integrations.cache.constants import CacheDefaults


class CacheKeyBuilder:
    """The only place a cache key string is assembled."""

    @staticmethod
    def entity_key(entity: str, entity_id: int, version: int) -> str:
        """Build a versioned key for one entity instance."""
        return f"{entity}:{entity_id}:v{version}:s{CacheDefaults.PAYLOAD_SCHEMA_VERSION}"

    @staticmethod
    def version_key(entity: str, entity_id: int) -> str:
        """Build the key holding the current generation of an entity."""
        return f"ver:{entity}:{entity_id}"

    @staticmethod
    def lock_key(entity: str, entity_id: int) -> str:
        """Build the key used to serialize loads across processes."""
        return f"lock:{entity}:{entity_id}"
'''


def cache_client() -> str:
    """Render integrations/cache/client.py."""
    return '''
"""Redis client with entity versioning and stampede protection."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from app.integrations.cache.config import cache_settings
from app.integrations.cache.constants import CacheDefaults
from app.integrations.cache.keys import CacheKeyBuilder
from app.core.base.markers import helper, integration

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
'''


def cache_dependencies() -> str:
    """Render integrations/cache/dependencies.py."""
    return '''
"""Dependency wiring for the cache integration."""

from fastapi import Request

from app.integrations.cache.client import CacheClient
from app.integrations.cache.config import cache_settings


async def get_cache(request: Request) -> CacheClient:
    """Provide the cache client backed by the process wide pool."""
    return CacheClient(request.app.state.redis, cache_settings.DEFAULT_TTL)
'''


def queue_constants() -> str:
    """Render integrations/queue/constants.py."""
    return '''
"""Constants owned by the queue integration."""

from enum import StrEnum


class QueueDefaults:
    """Numeric defaults owned by the queue integration."""

    MAX_RETRIES = 3
    RETRY_DELAY_MS = 30000
    DEFAULT_PREFETCH = 20


class QueueErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    PUBLISH_FAILED = "queue_publish_failed"
    NOT_CONNECTED = "queue_not_connected"


class ExchangeType(StrEnum):
    """Exchange kinds this integration declares."""

    TOPIC = "topic"
    DIRECT = "direct"
'''


def queue_config() -> str:
    """Render integrations/queue/config.py."""
    return '''
"""Settings owned by the queue integration."""

from pydantic import AmqpDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.queue.constants import QueueDefaults


class QueueConfig(BaseSettings):
    """Environment driven settings for RabbitMQ."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="QUEUE_", extra="ignore")

    URL: AmqpDsn = "amqp://guest:guest@localhost:5672/"
    PREFETCH: int = QueueDefaults.DEFAULT_PREFETCH
    MAX_RETRIES: int = QueueDefaults.MAX_RETRIES
    PUBLISHER_CONFIRMS: bool = True


queue_settings = QueueConfig()
'''


def queue_exceptions() -> str:
    """Render integrations/queue/exceptions.py."""
    return '''
"""Errors owned by the queue integration."""

from app.core.exceptions import IntegrationError
from app.integrations.queue.constants import QueueErrorCode


class PublishFailed(IntegrationError):
    """Raised when the broker did not confirm a published message."""

    code = QueueErrorCode.PUBLISH_FAILED
    message = "Failed to publish message"


class BrokerNotConnected(IntegrationError):
    """Raised when a publish is attempted before the connection is open."""

    code = QueueErrorCode.NOT_CONNECTED
    message = "Broker connection not established"
'''


def queue_topology() -> str:
    """Render integrations/queue/topology.py."""
    return '''
"""Exchange and queue declaration.

Queues are declared by their consumer, never by the publisher. A publisher that
knows queue names is coupled to its consumers, which defeats the exchange.
Dead letter routing is declared up front because retrofitting it later means
redeclaring a live queue.
"""

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue

from app.integrations.queue.constants import QueueDefaults


class QueueTopology:
    """Declares every exchange and queue the broker needs. Called by the consumer only."""

    @staticmethod
    async def declare_exchange(channel: AbstractChannel, name: str) -> AbstractExchange:
        """Declare a durable topic exchange."""
        return await channel.declare_exchange(name, aio_pika.ExchangeType.TOPIC, durable=True)

    @staticmethod
    async def declare_consumer_queue(
        channel: AbstractChannel,
        queue_name: str,
        exchange: str,
        routing_keys: list[str],
    ) -> AbstractQueue:
        """Declare a durable queue with retry and dead letter routing attached."""
        dlx = await channel.declare_exchange(f"{exchange}.dlx", aio_pika.ExchangeType.TOPIC, durable=True)

        retry = await channel.declare_queue(
            f"{queue_name}.retry",
            durable=True,
            arguments={
                "x-message-ttl": QueueDefaults.RETRY_DELAY_MS,
                "x-dead-letter-exchange": exchange,
            },
        )
        await retry.bind(dlx, routing_key="#")

        failed = await channel.declare_queue(f"{queue_name}.failed", durable=True)
        await failed.bind(dlx, routing_key="failed.#")

        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={"x-dead-letter-exchange": f"{exchange}.dlx"},
        )
        source = await QueueTopology.declare_exchange(channel, exchange)
        for key in routing_keys:
            await queue.bind(source, routing_key=key)
        return queue
'''


def queue_client() -> str:
    """Render integrations/queue/client.py."""
    return '''
"""RabbitMQ connection, publisher and consumer.

The API process only ever publishes (see app/main.py, app/lifespan.py). Only
app/worker.py — a separate process, started by scripts/start-worker.sh —
calls consume(). Mixing the two in one process means a slow consumer handler
can starve request handling; see references/messaging.md.
"""

import logging
from collections.abc import Awaitable, Callable

import aio_pika
import structlog
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from app.core.events import DomainEvent
from app.integrations.queue.config import queue_settings
from app.integrations.queue.exceptions import BrokerNotConnected, PublishFailed
from app.integrations.queue.topology import QueueTopology
from app.core.base.markers import helper, integration

logger = logging.getLogger(__name__)

ConsumerHandler = Callable[[bytes], Awaitable[None]]


class Broker:
    """Owns the AMQP connection; publishes persistent messages, consumes when asked."""

    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchanges: dict[str, AbstractExchange] = {}

    @integration
    async def connect(self) -> None:
        """Open a robust connection that reconnects on failure."""
        self._connection = await aio_pika.connect_robust(str(queue_settings.URL))
        self._channel = await self._connection.channel(
            publisher_confirms=queue_settings.PUBLISHER_CONFIRMS
        )
        await self._channel.set_qos(prefetch_count=queue_settings.PREFETCH)
        logger.info("broker connected")

    @integration
    async def close(self) -> None:
        """Close the connection during shutdown."""
        if self._connection is not None:
            await self._connection.close()

    @integration
    async def publish(self, exchange: str, event: DomainEvent) -> None:
        """Publish an event, carrying the current correlation_id, and wait for confirmation.

        correlation_id comes from whatever request bound it via
        RequestIdMiddleware (see references/logging.md) — falling back to
        the event's own id when publishing outside a request, e.g. from a
        worker or a seed script, so a message always carries some id a
        consumer can bind to its own logs.
        """
        if self._channel is None:
            raise BrokerNotConnected()

        target = await self._exchange(exchange)
        correlation_id = structlog.contextvars.get_contextvars().get("correlation_id", event.event_id)
        message = aio_pika.Message(
            body=event.model_dump_json().encode(),
            content_type="application/json",
            message_id=event.event_id,
            correlation_id=correlation_id,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        try:
            await target.publish(message, routing_key=event.routing_key)
        except aio_pika.exceptions.AMQPError as exc:
            raise PublishFailed(routing_key=event.routing_key) from exc

        logger.info("event published key=%s id=%s", event.routing_key, event.event_id)

    @integration
    async def consume(
        self,
        queue_name: str,
        exchange: str,
        routing_keys: list[str],
        handler: ConsumerHandler,
    ) -> None:
        """Declare the consumer's queue and run handler for every message until cancelled.

        Cap attempts before giving up on a message — retry forever hides a bug
        and burns capacity (see references/messaging.md). Nack without requeue
        past MAX_ATTEMPTS; the dead-letter topology declared alongside the
        queue routes it to <queue_name>.failed for a human to look at.

        Binds the correlation_id carried on the message (see publish() above)
        before calling handler, so every log line the handler emits — even a
        plain logging.getLogger(__name__) call — carries it too, the same way
        RequestIdMiddleware does for an HTTP request. See references/logging.md.
        """
        if self._channel is None:
            raise BrokerNotConnected()

        queue = await QueueTopology.declare_consumer_queue(self._channel, queue_name, exchange, routing_keys)
        async with queue.iterator() as messages:
            async for message in messages:
                async with message.process(requeue=False):
                    structlog.contextvars.clear_contextvars()
                    structlog.contextvars.bind_contextvars(
                        correlation_id=message.correlation_id or message.message_id,
                        message_id=message.message_id,
                    )
                    await handler(message.body)

    @helper
    async def _exchange(self, name: str) -> AbstractExchange:
        """Declare the exchange once and cache the handle."""
        if name not in self._exchanges:
            self._exchanges[name] = await QueueTopology.declare_exchange(self._channel, name)
        return self._exchanges[name]
'''


def queue_dependencies() -> str:
    """Render integrations/queue/dependencies.py."""
    return '''
"""Dependency wiring for the queue integration."""

from fastapi import Request

from app.integrations.queue.client import Broker


async def get_broker(request: Request) -> Broker:
    """Provide the process wide broker."""
    return request.app.state.broker
'''


def queue_idempotency(with_cache: bool) -> str:
    """Render integrations/queue/idempotency.py.

    Only app/worker.py wires this in (see root.worker) — a domain module
    never imports it directly, the same way a domain module never imports
    aio_pika directly. RedisIdempotencyStore is only generated when `cache`
    is also selected; the Protocol and the decorator work with any backend.
    """
    if with_cache:
        redis_import = "\nfrom redis.asyncio import Redis"
        redis_store = '''

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
'''
    else:
        redis_import = ""
        redis_store = ""

    return f'''
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
{redis_import}
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
{redis_store}'''


def storage_constants() -> str:
    """Render integrations/storage/constants.py."""
    return '''
"""Constants owned by the storage integration."""

from enum import StrEnum


class StorageDefaults:
    """Numeric defaults owned by the storage integration."""

    MAX_UPLOAD_BYTES = 50 * 1024 * 1024
    PRESIGNED_URL_TTL = 3600


class StorageErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UPLOAD_FAILED = "storage_upload_failed"
    OBJECT_NOT_FOUND = "storage_object_not_found"
'''


def storage_config() -> str:
    """Render integrations/storage/config.py."""
    return '''
"""Settings owned by the storage integration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageConfig(BaseSettings):
    """Environment driven settings for object storage."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="STORAGE_", extra="ignore")

    ENDPOINT: str = ""
    BUCKET: str = ""
    ACCESS_KEY: str = ""
    SECRET_KEY: str = ""
    REGION: str = "us-east-1"


storage_settings = StorageConfig()
'''


def storage_exceptions() -> str:
    """Render integrations/storage/exceptions.py."""
    return '''
"""Errors owned by the storage integration."""

from app.core.exceptions import IntegrationError, NotFoundError
from app.integrations.storage.constants import StorageErrorCode


class UploadFailed(IntegrationError):
    """Raised when an object could not be written to storage."""

    code = StorageErrorCode.UPLOAD_FAILED
    message = "Failed to upload object"


class ObjectNotFound(NotFoundError):
    """Raised when the requested key does not exist in the bucket."""

    code = StorageErrorCode.OBJECT_NOT_FOUND
    message = "Object not found"
'''


def storage_client() -> str:
    """Render integrations/storage/client.py."""
    return '''
"""Object storage client."""

import logging

import aioboto3

from app.integrations.storage.config import storage_settings
from app.integrations.storage.constants import StorageDefaults
from app.integrations.storage.exceptions import UploadFailed
from app.core.base.markers import helper, integration
from app.core.retry import retry

logger = logging.getLogger(__name__)


class StorageClient:
    """Wraps object storage access behind a narrow interface."""

    def __init__(self) -> None:
        self._session = aioboto3.Session()

    @integration
    async def close(self) -> None:
        """Release any pooled connection during shutdown."""
        return None

    @integration
    @retry(attempts=3, exceptions=(UploadFailed,))
    async def upload(self, key: str, body: bytes, content_type: str) -> str:
        """Store one object and return its key, retrying a transient failure up to twice more."""
        try:
            async with self._client() as client:
                await client.put_object(
                    Bucket=storage_settings.BUCKET,
                    Key=key,
                    Body=body,
                    ContentType=content_type,
                )
        except Exception as exc:
            raise UploadFailed(key=key) from exc

        logger.info("object uploaded key=%s", key)
        return key

    @integration
    async def presigned_url(self, key: str, ttl: int = StorageDefaults.PRESIGNED_URL_TTL) -> str:
        """Return a time limited URL granting read access to one object."""
        async with self._client() as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": storage_settings.BUCKET, "Key": key},
                ExpiresIn=ttl,
            )

    @helper
    def _client(self):
        """Open a configured storage client."""
        return self._session.client(
            "s3",
            endpoint_url=storage_settings.ENDPOINT or None,
            aws_access_key_id=storage_settings.ACCESS_KEY or None,
            aws_secret_access_key=storage_settings.SECRET_KEY or None,
            region_name=storage_settings.REGION,
        )
'''


def storage_dependencies() -> str:
    """Render integrations/storage/dependencies.py."""
    return '''
"""Dependency wiring for the storage integration."""

from fastapi import Request

from app.integrations.storage.client import StorageClient


async def get_storage(request: Request) -> StorageClient:
    """Provide the process wide storage client."""
    return request.app.state.storage
'''


def tracing_constants() -> str:
    """Render integrations/tracing/constants.py."""
    return '''
"""Constants owned by the tracing integration."""


class TracingDefaults:
    """Defaults owned by the tracing integration."""

    DEFAULT_OTLP_ENDPOINT = "http://localhost:4317"
'''


def tracing_config() -> str:
    """Render integrations/tracing/config.py."""
    return '''
"""Settings owned by the tracing integration."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.tracing.constants import TracingDefaults


class TracingConfig(BaseSettings):
    """Environment driven settings for OpenTelemetry export."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TRACING_", extra="ignore")

    ENABLED: bool = True
    OTLP_ENDPOINT: str = TracingDefaults.DEFAULT_OTLP_ENDPOINT


tracing_settings = TracingConfig()
'''


def tracing_client() -> str:
    """Render integrations/tracing/client.py."""
    return '''
"""OpenTelemetry tracer provider, wired once at process startup.

Kept as a leaf integration like cache, queue and storage: it owns its own
settings and never imports a domain module. Domain and root code only ever
see it through app.state.tracer_provider, set in lifespan.py.
"""

import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.integrations.tracing.config import tracing_settings

logger = logging.getLogger(__name__)


def setup_tracing(app: FastAPI, service_name: str, environment: str) -> TracerProvider | None:
    """Configure the global tracer provider and instrument the ASGI app."""
    if not tracing_settings.ENABLED:
        return None

    resource = Resource.create({"service.name": service_name, "deployment.environment": environment})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=tracing_settings.OTLP_ENDPOINT)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)

    logger.info("tracing initialized endpoint=%s", tracing_settings.OTLP_ENDPOINT)
    return provider


def shutdown_tracing(provider: TracerProvider | None) -> None:
    """Flush buffered spans and release exporter resources."""
    if provider is not None:
        provider.shutdown()
'''


RENDERERS = {
    "tracing": {
        "constants": tracing_constants,
        "config": tracing_config,
        "client": tracing_client,
    },
    "cache": {
        "constants": cache_constants,
        "config": cache_config,
        "exceptions": cache_exceptions,
        "keys": cache_keys,
        "client": cache_client,
        "dependencies": cache_dependencies,
    },
    "queue": {
        "constants": queue_constants,
        "config": queue_config,
        "exceptions": queue_exceptions,
        "topology": queue_topology,
        "client": queue_client,
        "dependencies": queue_dependencies,
    },
    "storage": {
        "constants": storage_constants,
        "config": storage_config,
        "exceptions": storage_exceptions,
        "client": storage_client,
        "dependencies": storage_dependencies,
    },
}
