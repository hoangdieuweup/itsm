"""Dependency wiring for the dx_core integration."""

from app.integrations.dx_core.client import DxCoreClient


async def get_dx_core_client() -> DxCoreClient:
    """Provide the DX OAuth2 client.

    No shared connection pool: DxCoreClient opens one short-lived httpx
    client per call (see its own module docstring for why — at most two
    calls per login, one per refresh, so a pool would only buy a saved
    connect() this integration doesn't otherwise need).
    """
    return DxCoreClient()
