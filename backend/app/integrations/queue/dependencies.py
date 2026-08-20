"""Dependency wiring for the queue integration."""

from fastapi import Request

from app.integrations.queue.client import Broker


async def get_broker(request: Request) -> Broker:
    """Provide the process wide broker."""
    return request.app.state.broker
