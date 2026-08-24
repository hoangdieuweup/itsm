"""Dependency wiring for the telegram integration."""

from app.integrations.telegram.client import TelegramClient


async def get_telegram_client() -> TelegramClient:
    """Provide the Telegram Bot API client. No transport override in production."""
    return TelegramClient()
