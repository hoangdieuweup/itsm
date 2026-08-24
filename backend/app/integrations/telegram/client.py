"""Telegram Bot API client. HTTP only — no database, no business logic."""

import httpx

from app.core.base.markers import integration
from app.integrations.telegram.config import telegram_settings
from app.integrations.telegram.exceptions import (
    InvalidTelegramCredential,
    TelegramApiUnavailable,
    TelegramRejected,
)


class TelegramClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @integration
    async def send_message(self, *, bot_token: str, chat_id: str, text: str) -> None:
        """POST /bot{token}/sendMessage. Checks the response's own
        {"ok": bool, ...} envelope, not just HTTP status — same lesson
        Cloudflare's v4 API already taught this codebase."""
        try:
            async with httpx.AsyncClient(
                base_url=str(telegram_settings.API_BASE_URL), transport=self._transport
            ) as client:
                response = await client.post(
                    f"/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                    timeout=telegram_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise TelegramApiUnavailable() from exc

        if response.status_code in (401, 403):
            raise InvalidTelegramCredential()
        if response.status_code >= 500:
            raise TelegramApiUnavailable(status_code=response.status_code)
        body = response.json()
        if not body.get("ok", False):
            raise TelegramRejected(message=body.get("description", "Telegram rejected this message"))
