"""Consumer process entry point. Runs separately from the API — see scripts/start-worker.sh.

Owns nothing the API doesn't already own: same settings, same use cases. A
slow or crashing consumer must never be able to starve request handling in
the API process, which is why this is its own process, not a background task
bolted onto app/main.py.
"""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable

from app.integrations.cache.client import RedisConnectionFactory
from app.integrations.queue.client import Broker
from app.integrations.queue.idempotency import RedisIdempotencyStore, idempotent
from app.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

QUEUE_PREFIX = "app.work"
EXCHANGES = ["auth"]


async def handle_message(body: bytes) -> None:
    """Route one message to the use case that owns it.

    Placeholder — dispatch on a type field in the message body to whichever
    module should react to it. Keep this a dispatch table, not a growing
    if/elif chain: {"identity.created": handle_identity_created, ...}.
    """
    logger.info("message received bytes=%s", len(body))


async def consume_one(broker: Broker, exchange: str, handler: Callable[[bytes], Awaitable[None]]) -> None:
    """Consume everything published on one module's exchange."""
    await broker.consume(f"{QUEUE_PREFIX}.{exchange}", exchange, ["#"], handler)


async def main() -> None:
    """Connect, consume every module's exchange until stopped, then close cleanly."""
    broker = Broker()
    await broker.connect()

    redis = RedisConnectionFactory.create()
    handler = idempotent(RedisIdempotencyStore(redis))(handle_message)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    tasks = [asyncio.create_task(consume_one(broker, exchange, handler)) for exchange in EXCHANGES]
    logger.info("worker started exchanges=%s", EXCHANGES)

    await stop.wait()
    logger.info("worker stopping")
    for task in tasks:
        task.cancel()
    await broker.close()
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
