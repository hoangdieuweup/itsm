"""Unit tests for app.modules.cloudflare.client — no real network calls, a
fake httpx transport stands in for Cloudflare's API."""

import httpx
import pytest

from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.exceptions import CloudflareApiUnavailable, InvalidCloudflareToken


class TestTestConnection:
    async def test_succeeds_on_200_with_success_true(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["account.id"] == "acc1"
            assert request.headers["authorization"] == "Bearer good-token"
            return httpx.Response(200, json={"success": True, "result": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        await client.test_connection(cf_account_id="acc1", api_token="good-token")

    async def test_raises_invalid_token_on_401(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"success": False, "errors": [{"message": "bad token"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidCloudflareToken):
            await client.test_connection(cf_account_id="acc1", api_token="bad")

    async def test_raises_invalid_token_on_200_with_success_false(self) -> None:
        """Cloudflare's v4 API can return HTTP 200 with success=false — status
        alone is not enough to decide whether the token was accepted."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "errors": [{"message": "insufficient scope"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidCloudflareToken):
            await client.test_connection(cf_account_id="acc1", api_token="wrong-scope")

    async def test_raises_unavailable_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.test_connection(cf_account_id="acc1", api_token="x")

    async def test_raises_unavailable_on_500(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"success": False, "errors": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.test_connection(cf_account_id="acc1", api_token="x")
