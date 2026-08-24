"""Unit tests for app.integrations.loki.client — no real network calls,
a fake httpx transport stands in for a Loki API. TestTail uses a real,
local, in-process WebSocket server instead of mocking websockets.connect
internals — more faithful to how the client actually behaves."""

import asyncio
import contextlib
import json
from datetime import UTC, datetime

import httpx
import pytest
import yaml
from websockets.asyncio.server import serve as ws_serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosedOK
from websockets.http11 import Response

from app.integrations.loki.client import LokiClient
from app.integrations.loki.exceptions import InvalidLokiCredential, LokiApiUnavailable, LokiQueryRejected
from app.integrations.loki.schemas import LokiLogEntry

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
            return httpx.Response(
                200, json={"status": "success", "data": {"resultType": "streams", "result": []}}
            )

        client = LokiClient(transport=httpx.MockTransport(handler))
        result = await client.query_range(
            endpoint_url="http://loki:3100",
            query="{}",
            start=START,
            end=END,
            tenant_id=None,
            auth_header=None,
        )
        assert result.entries == []

    async def test_no_auth_header_when_none_given(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "authorization" not in request.headers
            assert "x-scope-orgid" not in request.headers
            return httpx.Response(
                200, json={"status": "success", "data": {"resultType": "streams", "result": []}}
            )

        client = LokiClient(transport=httpx.MockTransport(handler))
        await client.query_range(
            endpoint_url="http://loki:3100",
            query="{}",
            start=START,
            end=END,
            tenant_id=None,
            auth_header=None,
        )

    async def test_401_raises_invalid_credential(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"status": "error", "error": "no orgId"})

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidLokiCredential):
            await client.query_range(
                endpoint_url="http://loki:3100",
                query="{}",
                start=START,
                end=END,
                tenant_id=None,
                auth_header=None,
            )

    async def test_403_raises_invalid_credential(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"status": "error", "error": "forbidden"})

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidLokiCredential):
            await client.query_range(
                endpoint_url="http://loki:3100",
                query="{}",
                start=START,
                end=END,
                tenant_id=None,
                auth_header=None,
            )

    async def test_400_raises_rejected_with_loki_message(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400, json={"status": "error", "error": "parse error: unexpected IDENTIFIER"}
            )

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LokiQueryRejected, match="parse error: unexpected IDENTIFIER"):
            await client.query_range(
                endpoint_url="http://loki:3100",
                query="{bad",
                start=START,
                end=END,
                tenant_id=None,
                auth_header=None,
            )

    async def test_500_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"status": "error", "error": "internal"})

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LokiApiUnavailable):
            await client.query_range(
                endpoint_url="http://loki:3100",
                query="{}",
                start=START,
                end=END,
                tenant_id=None,
                auth_header=None,
            )

    async def test_transport_failure_raises_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LokiApiUnavailable):
            await client.query_range(
                endpoint_url="http://loki:3100",
                query="{}",
                start=START,
                end=END,
                tenant_id=None,
                auth_header=None,
            )


class TestTail:
    async def test_streams_flattened_entries(self) -> None:
        received_headers: dict = {}

        async def handler(websocket) -> None:
            received_headers.update(websocket.request.headers)
            await websocket.send(
                json.dumps(
                    {"streams": [{"stream": {"job": "api"}, "values": [["1700000001000000000", "first"]]}]}
                )
            )
            await websocket.send(
                json.dumps(
                    {"streams": [{"stream": {"job": "api"}, "values": [["1700000002000000000", "second"]]}]}
                )
            )
            await asyncio.sleep(0.2)

        async with ws_serve(handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            client = LokiClient()
            entries: list[LokiLogEntry] = []
            with contextlib.suppress(ConnectionClosedOK):
                async for entry in client.tail(
                    endpoint_url=f"http://localhost:{port}",
                    query='{job="api"}',
                    tenant_id="tenant-a",
                    auth_header="Bearer tok",
                    limit=10,
                ):
                    entries.append(entry)
                    if len(entries) == 2:
                        break

        assert [e.line for e in entries] == ["first", "second"]
        assert received_headers.get("authorization") == "Bearer tok"
        assert received_headers.get("x-scope-orgid") == "tenant-a"

    async def test_401_handshake_raises_invalid_credential(self) -> None:
        async def handler(websocket) -> None:
            return None

        def reject(connection, request) -> Response:
            return Response(401, "Unauthorized", Headers())

        async with ws_serve(handler, "localhost", 0, process_request=reject) as server:
            port = server.sockets[0].getsockname()[1]
            client = LokiClient()
            with pytest.raises(InvalidLokiCredential):
                async for _ in client.tail(
                    endpoint_url=f"http://localhost:{port}", query="{}", tenant_id=None, auth_header=None
                ):
                    pass

    async def test_400_handshake_raises_query_rejected(self) -> None:
        async def handler(websocket) -> None:
            return None

        def reject(connection, request) -> Response:
            return Response(400, "Bad Request", Headers())

        async with ws_serve(handler, "localhost", 0, process_request=reject) as server:
            port = server.sockets[0].getsockname()[1]
            client = LokiClient()
            with pytest.raises(LokiQueryRejected):
                async for _ in client.tail(
                    endpoint_url=f"http://localhost:{port}", query="{bad", tenant_id=None, auth_header=None
                ):
                    pass

    async def test_connection_refused_raises_unavailable(self) -> None:
        client = LokiClient()
        with pytest.raises(LokiApiUnavailable):
            async for _ in client.tail(
                endpoint_url="http://localhost:1", query="{}", tenant_id=None, auth_header=None
            ):
                pass


class TestUpsertRuleGroup:
    async def test_success_posts_yaml_rule_group(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/loki/api/v1/rules/itsm"
            assert request.method == "POST"
            assert request.headers["content-type"] == "application/yaml"
            captured["body"] = yaml.safe_load(request.read())
            return httpx.Response(202)

        client = LokiClient(transport=httpx.MockTransport(handler))
        await client.upsert_rule_group(
            endpoint_url="http://loki:3100",
            namespace="itsm",
            group_name="alert-rule-abc",
            rule_name="alert-rule-abc",
            expr='{app="x"} |= "error"',
            for_duration="5m",
            labels={"app_alert_rule_id": "abc"},
            auth_header=None,
        )
        assert captured["body"]["name"] == "alert-rule-abc"
        assert captured["body"]["rules"][0]["alert"] == "alert-rule-abc"
        assert captured["body"]["rules"][0]["expr"] == '{app="x"} |= "error"'
        assert captured["body"]["rules"][0]["for"] == "5m"
        assert captured["body"]["rules"][0]["labels"] == {"app_alert_rule_id": "abc"}

    async def test_sends_auth_header_when_given(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(202)

        client = LokiClient(transport=httpx.MockTransport(handler))
        await client.upsert_rule_group(
            endpoint_url="http://loki:3100",
            namespace="itsm",
            group_name="g",
            rule_name="r",
            expr="{}",
            for_duration="5m",
            labels={},
            auth_header="Bearer secret",
        )
        assert captured["auth"] == "Bearer secret"

    async def test_unauthorized_raises_invalid_credential(self) -> None:
        client = LokiClient(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="unauthorized")))
        with pytest.raises(InvalidLokiCredential):
            await client.upsert_rule_group(
                endpoint_url="http://loki:3100",
                namespace="itsm",
                group_name="g",
                rule_name="r",
                expr="{}",
                for_duration="5m",
                labels={},
                auth_header=None,
            )

    async def test_rejected_raises(self) -> None:
        client = LokiClient(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad LogQL")))
        with pytest.raises(LokiQueryRejected):
            await client.upsert_rule_group(
                endpoint_url="http://loki:3100",
                namespace="itsm",
                group_name="g",
                rule_name="r",
                expr="{{bad",
                for_duration="5m",
                labels={},
                auth_header=None,
            )

    async def test_unavailable_raises_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = LokiClient(transport=httpx.MockTransport(handler))
        with pytest.raises(LokiApiUnavailable):
            await client.upsert_rule_group(
                endpoint_url="http://loki:3100",
                namespace="itsm",
                group_name="g",
                rule_name="r",
                expr="{}",
                for_duration="5m",
                labels={},
                auth_header=None,
            )

    async def test_unavailable_raises_on_5xx(self) -> None:
        client = LokiClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
        with pytest.raises(LokiApiUnavailable):
            await client.upsert_rule_group(
                endpoint_url="http://loki:3100",
                namespace="itsm",
                group_name="g",
                rule_name="r",
                expr="{}",
                for_duration="5m",
                labels={},
                auth_header=None,
            )
