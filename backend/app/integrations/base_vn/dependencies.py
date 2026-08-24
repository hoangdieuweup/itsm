"""Dependency wiring for the base_vn integration."""

from app.integrations.base_vn.client import BaseVnClient


async def get_base_vn_client() -> BaseVnClient:
    """Provide the Base.vn Incoming Webhook client. No transport override in production."""
    return BaseVnClient()
