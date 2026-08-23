"""Unit tests for app.integrations.cloudflare.client — no real network calls,
a fake httpx transport stands in for Cloudflare's API."""

import json

import httpx
import pytest

from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.exceptions import (
    CloudflareApiUnavailable,
    CloudflareDnsOperationRejected,
    InvalidCloudflareToken,
)
from app.integrations.cloudflare.schemas import ZoneOption


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


class TestListZones:
    async def test_returns_zones_from_single_page(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["account.id"] == "acc1"
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": [{"id": "z1", "name": "example.com"}],
                    "result_info": {"page": 1, "total_pages": 1},
                },
            )

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        zones = await client.list_zones(cf_account_id="acc1", api_token="good-token")

        assert zones == [ZoneOption(id="z1", name="example.com")]

    async def test_walks_every_page(self) -> None:
        pages = {
            1: {
                "success": True,
                "result": [{"id": "z1", "name": "a.com"}],
                "result_info": {"page": 1, "total_pages": 2},
            },
            2: {
                "success": True,
                "result": [{"id": "z2", "name": "b.com"}],
                "result_info": {"page": 2, "total_pages": 2},
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params["page"])
            return httpx.Response(200, json=pages[page])

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        zones = await client.list_zones(cf_account_id="acc1", api_token="x")

        assert {z.id for z in zones} == {"z1", "z2"}

    async def test_raises_invalid_token_on_success_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "errors": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidCloudflareToken):
            await client.list_zones(cf_account_id="acc1", api_token="bad")

    async def test_raises_unavailable_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.list_zones(cf_account_id="acc1", api_token="x")


class TestCreateDnsRecord:
    async def test_returns_cf_record_id_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/client/v4/zones/zone1/dns_records"
            return httpx.Response(200, json={"success": True, "result": {"id": "rec-123"}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        record_id = await client.create_dns_record(
            zone_id="zone1",
            api_token="x",
            record_type="A",
            name="app",
            content="1.2.3.4",
            priority=None,
            proxied=True,
            ttl=1,
        )

        assert record_id == "rec-123"

    async def test_raises_rejected_on_success_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "errors": [{"message": "invalid content"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.create_dns_record(
                zone_id="zone1",
                api_token="x",
                record_type="A",
                name="app",
                content="bad",
                priority=None,
                proxied=False,
                ttl=1,
            )

    async def test_raises_unavailable_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.create_dns_record(
                zone_id="zone1",
                api_token="x",
                record_type="A",
                name="app",
                content="1.2.3.4",
                priority=None,
                proxied=False,
                ttl=1,
            )


class TestUpdateDnsRecord:
    async def test_succeeds(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            assert request.url.path == "/client/v4/zones/zone1/dns_records/rec-123"
            return httpx.Response(200, json={"success": True, "result": {"id": "rec-123"}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        await client.update_dns_record(
            zone_id="zone1",
            cf_record_id="rec-123",
            api_token="x",
            record_type="A",
            name="app",
            content="5.6.7.8",
            priority=None,
            proxied=True,
            ttl=1,
        )

    async def test_raises_rejected_on_4xx(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"success": False, "errors": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.update_dns_record(
                zone_id="zone1",
                cf_record_id="rec-123",
                api_token="x",
                record_type="A",
                name="app",
                content="x",
                priority=None,
                proxied=False,
                ttl=1,
            )


class TestDeleteDnsRecord:
    async def test_succeeds(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            assert request.url.path == "/client/v4/zones/zone1/dns_records/rec-123"
            return httpx.Response(200, json={"success": True, "result": {"id": "rec-123"}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        await client.delete_dns_record(zone_id="zone1", cf_record_id="rec-123", api_token="x")

    async def test_raises_unavailable_on_500(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"success": False})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.delete_dns_record(zone_id="zone1", cf_record_id="rec-123", api_token="x")


class TestCreateTunnel:
    async def test_returns_id_and_hardcodes_config_src(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/client/v4/accounts/acc-1/cfd_tunnel"
            body = json.loads(request.content)
            assert body["config_src"] == "cloudflare"
            assert body["name"] == "my-tunnel"
            return httpx.Response(200, json={"success": True, "result": {"id": "tun-1"}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        tunnel_id = await client.create_tunnel(cf_account_id="acc-1", api_token="tok", name="my-tunnel")
        assert tunnel_id == "tun-1"

    async def test_raises_rejected_on_success_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"success": False, "errors": [{"message": "bad"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.create_tunnel(cf_account_id="acc-1", api_token="tok", name="my-tunnel")

    async def test_raises_unavailable_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.create_tunnel(cf_account_id="acc-1", api_token="tok", name="my-tunnel")


class TestGetTunnelToken:
    async def test_returns_plaintext_token(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/client/v4/accounts/acc-1/cfd_tunnel/tun-1/token"
            return httpx.Response(200, json={"success": True, "result": "eyJ0..."})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        token = await client.get_tunnel_token(cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok")
        assert token == "eyJ0..."


class TestListTunnelConnections:
    async def test_returns_raw_list(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/client/v4/accounts/acc-1/cfd_tunnel/tun-1/connections"
            return httpx.Response(200, json={"success": True, "result": [{"id": "conn-1"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        connections = await client.list_tunnel_connections(
            cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok"
        )
        assert connections == [{"id": "conn-1"}]

    async def test_returns_empty_list_when_down(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "result": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        connections = await client.list_tunnel_connections(
            cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok"
        )
        assert connections == []


class TestGetTunnelConfiguration:
    async def test_returns_ingress_array(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/client/v4/accounts/acc-1/cfd_tunnel/tun-1/configurations"
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {"config": {"ingress": [{"hostname": "a.example.com", "service": "http://x"}]}},
                },
            )

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        ingress = await client.get_tunnel_configuration(
            cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok"
        )
        assert ingress == [{"hostname": "a.example.com", "service": "http://x"}]

    async def test_returns_empty_list_for_new_tunnel(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "result": {"config": {}}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        ingress = await client.get_tunnel_configuration(
            cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok"
        )
        assert ingress == []


class TestPutTunnelConfiguration:
    async def test_sends_ingress_array(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PUT"
            assert request.url.path == "/client/v4/accounts/acc-1/cfd_tunnel/tun-1/configurations"
            body = json.loads(request.content)
            assert body["config"]["ingress"][0]["hostname"] == "a.example.com"
            assert body["config"]["ingress"][-1] == {"service": "http_status:404"}
            return httpx.Response(200, json={"success": True, "result": {}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        await client.put_tunnel_configuration(
            cf_account_id="acc-1",
            cf_tunnel_id="tun-1",
            api_token="tok",
            ingress=[{"hostname": "a.example.com", "service": "http://x"}, {"service": "http_status:404"}],
        )

    async def test_raises_rejected_on_success_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"success": False, "errors": [{"message": "bad"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.put_tunnel_configuration(
                cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok", ingress=[]
            )


class TestDeleteTunnel:
    async def test_succeeds(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            assert request.url.path == "/client/v4/accounts/acc-1/cfd_tunnel/tun-1"
            return httpx.Response(200, json={"success": True, "result": {}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        await client.delete_tunnel(cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok")

    async def test_raises_unavailable_on_5xx(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"success": False})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.delete_tunnel(cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok")
