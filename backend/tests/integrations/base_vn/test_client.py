"""Unit tests for app.integrations.base_vn.client — no real network calls,
a fake httpx transport stands in for a Base.vn Incoming Webhook."""

import httpx
import pytest

from app.integrations.base_vn.client import BaseVnClient
from app.integrations.base_vn.exceptions import BaseVnApiUnavailable, BaseVnRejected


class TestSend:
    async def test_succeeds_on_2xx(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert b"base_content" in request.read()
            return httpx.Response(200, json={"success": True})

        client = BaseVnClient(transport=httpx.MockTransport(handler))
        await client.send(webhook_url="http://base.vn/webhook/abc", base_content="hello")

    async def test_4xx_raises_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"success": False, "message": "bad payload"})

        client = BaseVnClient(transport=httpx.MockTransport(handler))
        with pytest.raises(BaseVnRejected):
            await client.send(webhook_url="http://base.vn/webhook/abc", base_content="hello")

    async def test_5xx_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client = BaseVnClient(transport=httpx.MockTransport(handler))
        with pytest.raises(BaseVnApiUnavailable):
            await client.send(webhook_url="http://base.vn/webhook/abc", base_content="hello")

    async def test_transport_failure_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = BaseVnClient(transport=httpx.MockTransport(handler))
        with pytest.raises(BaseVnApiUnavailable):
            await client.send(webhook_url="http://base.vn/webhook/abc", base_content="hello")
