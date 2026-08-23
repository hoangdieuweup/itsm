"""Unit tests for app.integrations.loki.client — no real network calls,
a fake httpx transport stands in for a Loki API."""

from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.loki.client import LokiClient
from app.integrations.loki.exceptions import InvalidLokiCredential, LokiApiUnavailable, LokiQueryRejected

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 1, 1, tzinfo=UTC)


class TestQueryRange:
    async def test_flattens_and_sorts_multi_stream_results(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/loki/api/v1/query_range"
            assert request.headers["authorization"] == "Bearer tok"
            assert request.headers["x-scope-orgid"] == "tenant-a"
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "streams",
                        "result": [
                            {"stream": {"job": "api"}, "values": [["1700000002000000000", "second"]]},
                            {"stream": {"job": "web"}, "values": [["1700000001000000000", "first"]]},
                        ],
                    },
                },
            )

        client = LokiClient(transport=httpx.MockTransport(handler))
        result = await client.query_range(
            endpoint_url="http://loki:3100",
            query='{job="api"}',
            start=START,
            end=END,
            tenant_id="tenant-a",
            auth_header="Bearer tok",
        )
        assert [e.line for e in result.entries] == ["first", "second"]
        assert result.entries[0].labels == {"job": "web"}

    async def test_empty_result(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "success", "data": {"resultType": "streams", "result": []}})

        client = LokiClient(transport=httpx.MockTransport(handler))
        result = await client.query_range(
            endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
        )
        assert result.entries == []

    async def test_no_auth_header_when_none_given(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "authorization" not in request.headers
            assert "x-scope-orgid" not in request.headers
            return httpx.Response(200, json={"status": "success", "data": {"resultType": "streams", "result": []}})

        client = LokiClient(transport=httpx.MockTransport(handler))
        await client.query_range(
            endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
        )

    async def test_401_raises_invalid_credential(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"status": "error", "error": "no orgId"})

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidLokiCredential):
            await client.query_range(
                endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
            )

    async def test_403_raises_invalid_credential(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"status": "error", "error": "forbidden"})

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidLokiCredential):
            await client.query_range(
                endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
            )

    async def test_400_raises_rejected_with_loki_message(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"status": "error", "error": "parse error: unexpected IDENTIFIER"})

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LokiQueryRejected, match="parse error: unexpected IDENTIFIER"):
            await client.query_range(
                endpoint_url="http://loki:3100", query="{bad", start=START, end=END, tenant_id=None, auth_header=None
            )

    async def test_500_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"status": "error", "error": "internal"})

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LokiApiUnavailable):
            await client.query_range(
                endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
            )

    async def test_transport_failure_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LokiApiUnavailable):
            await client.query_range(
                endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
            )
