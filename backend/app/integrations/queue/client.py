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

from app.events import DomainEvent
from app.integrations.queue.config import queue_settings
from app.integrations.queue.exceptions import BrokerNotConnected, PublishFailed
from app.integrations.queue.topology import QueueTopology
from app.markers import helper, integration

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
        self._channel = await self._connection.channel(publisher_confirms=queue_settings.PUBLISHER_CONFIRMS)
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
