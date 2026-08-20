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
