"""Event mechanism. Concrete events belong to the module that publishes them."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DomainEvent(BaseModel):
    """Base class carrying the identity every consumer needs to deduplicate."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event to a broker."""
        raise NotImplementedError


Handler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """Dispatches events in process to handlers registered by type."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> None:
        """Register one handler for one event type."""
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Deliver an event without letting a handler failure reach the caller."""
        handlers = self._handlers.get(type(event), [])
        results = await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.exception("event handler failed event=%s", type(event).__name__)


event_bus = EventBus()


async def get_event_bus() -> EventBus:
    """Provide the shared event bus."""
    return event_bus
