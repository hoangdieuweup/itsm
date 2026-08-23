"""Dependency wiring for the cloudflare integration."""

from app.integrations.cloudflare.client import CloudflareClient


async def get_cloudflare_client() -> CloudflareClient:
    """Provide the Cloudflare API client. No transport override in production."""
    return CloudflareClient()
