"""Dependency wiring for the dx_core integration."""

from app.integrations.dx_core.client import DxCoreClient


async def get_dx_core_client() -> DxCoreClient:
    """Provide the DX OAuth2 client.

    No shared connection pool is needed yet since every method is a stub —
    once httpx calls are implemented, wire a process wide client into
    app.state from lifespan.py the same way the cache integration does.
    """
    return DxCoreClient()
