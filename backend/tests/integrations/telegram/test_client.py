"""Unit tests for app.integrations.telegram.client — no real network calls,
a fake httpx transport stands in for the Telegram Bot API."""

import httpx
import pytest

from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.exceptions import (
    InvalidTelegramCredential,
    TelegramApiUnavailable,
    TelegramRejected,
)


class TestSendMessage:
    async def test_succeeds_on_ok_true(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/bottok123/sendMessage"
            body = request.read()
            assert b"chat-1" in body
            assert b"hello" in body
            return httpx.Response(200, json={"ok": True, "result": {}})

        client = TelegramClient(transport=httpx.MockTransport(handler))
        await client.send_message(bot_token="tok123", chat_id="chat-1", text="hello")

    async def test_401_raises_invalid_credential(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"ok": False, "error_code": 401, "description": "Unauthorized"})

        client = TelegramClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidTelegramCredential):
            await client.send_message(bot_token="bad", chat_id="chat-1", text="hello")

    async def test_ok_false_raises_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"ok": False, "error_code": 400, "description": "chat not found"})

        client = TelegramClient(transport=httpx.MockTransport(handler))
        with pytest.raises(TelegramRejected):
            await client.send_message(bot_token="tok123", chat_id="wrong", text="hello")

    async def test_transport_failure_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = TelegramClient(transport=httpx.MockTransport(handler))
        with pytest.raises(TelegramApiUnavailable):
            await client.send_message(bot_token="tok123", chat_id="chat-1", text="hello")
