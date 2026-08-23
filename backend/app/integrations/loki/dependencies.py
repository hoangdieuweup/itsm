"""Dependency wiring for the loki integration."""

from app.integrations.loki.client import LokiClient


async def get_loki_client() -> LokiClient:
    """Provide the Loki API client. No transport override in production."""
    return LokiClient()
