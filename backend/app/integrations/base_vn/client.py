"""Base.vn Incoming Webhook client. HTTP only — no database, no business logic."""

import httpx

from app.core.base.markers import integration
from app.integrations.base_vn.config import base_vn_settings
from app.integrations.base_vn.exceptions import BaseVnApiUnavailable, BaseVnRejected


class BaseVnClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @integration
    async def send(self, *, webhook_url: str, base_content: str) -> None:
        """POST webhook_url with {"base_content": ...} — the field name
        Base.vn's own Incoming Webhook mechanism expects. Every channel's
        webhook_url is a distinct, user-provided full URL (no fixed host),
        so this client is constructed with no base_url and posts to the
        full URL directly."""
        try:
            async with httpx.AsyncClient(transport=self._transport) as client:
                response = await client.post(
                    webhook_url,
                    json={"base_content": base_content},
                    timeout=base_vn_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise BaseVnApiUnavailable() from exc

        if response.status_code >= 500:
            raise BaseVnApiUnavailable(status_code=response.status_code)
        if response.is_error:
            raise BaseVnRejected()
