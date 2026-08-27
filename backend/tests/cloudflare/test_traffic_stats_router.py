"""Integration tests for GET /environments/{id}/cloudflare-traffic-stats —
the GraphQL Analytics (Free-plan compatible) substitute for the Audit Log
tab. Mirrors test_audit_logs_router.py's exact fixtures/helpers via import."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.integrations.cloudflare.dependencies import get_cloudflare_client
from app.integrations.cloudflare.schemas import CloudflareTrafficStats, ZoneOption
from app.main import app
from app.modules.cloudflare.config import cloudflare_settings
from tests.cloudflare.test_router import FakeCloudflareClient, _bind_environment, _login_with_permissions


@pytest.fixture(autouse=True)
def _cloudflare_fernet_key(monkeypatch) -> None:
    """_bind_environment creates a real Cloudflare account, which really
    encrypts its token — needs a real 32-byte Fernet key, same as
    test_router.py's own fixture of this name."""
    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s=")


class FakeTrafficStatsClient(FakeCloudflareClient):
    def __init__(self, stats: CloudflareTrafficStats | None = None) -> None:
        super().__init__(zones=[ZoneOption(id="z1", name="example.com")])
        self._stats = stats
        self.calls: list[dict] = []

    async def get_zone_traffic_stats(self, *, zone_id, api_token, hostname, since, until):
        self.calls.append({"zone_id": zone_id, "hostname": hostname})
        return self._stats


class TestGetCloudflareTrafficStatsRoute:
    async def test_requires_view_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id, _account_id, _owner_id = await _bind_environment(
            client, engine, cf_client=FakeTrafficStatsClient()
        )
        await _login_with_permissions(client, engine, permissions=[], email="noperm@x.com")

        response = await client.get(f"/api/v1/environments/{environment_id}/cloudflare-traffic-stats")
        assert response.status_code == 403

        del app.dependency_overrides[get_cloudflare_client]

    async def test_404s_for_unbound_environment(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(
            client,
            engine,
            permissions=[("cloudflare_account", "view"), ("project", "create"), ("environment", "create")],
            email="viewer@x.com",
        )
        project_resp = await client.post("/api/v1/projects", json={"name": "Unbound"})
        project_id = project_resp.json()["data"]["id"]
        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "Dev"}
        )
        environment_id = env_resp.json()["data"]["id"]

        response = await client.get(f"/api/v1/environments/{environment_id}/cloudflare-traffic-stats")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "cloudflare_config_not_found"

    async def test_422s_when_base_url_not_configured(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id, _account_id, _owner_id = await _bind_environment(
            client, engine, cf_client=FakeTrafficStatsClient()
        )

        response = await client.get(f"/api/v1/environments/{environment_id}/cloudflare-traffic-stats")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cloudflare_environment_base_url_not_configured"

        del app.dependency_overrides[get_cloudflare_client]

    async def test_returns_stats_for_bound_environment_with_base_url(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """Sets baseUrl at environment-creation time (not via a later PATCH)
        deliberately — EnvironmentRepository.update() never invalidates the
        cache-aside get_by_id entry (same accepted "stale for up to
        TTL_SECONDS after a write" trade-off CloudflareAccountRepository.update
        already makes), so a create-then-PATCH-then-read-through-a-different-
        cache-populating-call sequence would flake on a warm cache within
        this same test process."""
        stats = CloudflareTrafficStats(
            hostname="app.example.com", total_requests=42, total_bytes=1024, buckets=[], status_codes=[]
        )
        fake_client = FakeTrafficStatsClient(stats=stats)
        app.dependency_overrides[get_cloudflare_client] = lambda: fake_client
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("cloudflare_account", "create"),
                ("cloudflare_account", "read"),
                ("cloudflare_config", "manage"),
                ("cloudflare_traffic", "read"),
                ("project", "create"),
                ("environment", "create"),
                ("environment", "read"),
            ],
        )
        account_resp = await client.post(
            "/api/v1/cloudflare-accounts", json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"}
        )
        account_id = account_resp.json()["data"]["id"]
        project_resp = await client.post("/api/v1/projects", json={"name": "Site"})
        project_id = project_resp.json()["data"]["id"]
        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments",
            json={"type": "dev", "name": "Dev", "baseUrl": "https://app.example.com"},
        )
        environment_id = env_resp.json()["data"]["id"]
        bind_resp = await client.post(
            "/api/v1/cloudflare-configs",
            json={"environmentId": environment_id, "cloudflareAccountId": account_id, "zoneId": "z1"},
        )
        assert bind_resp.status_code == 200, bind_resp.text

        response = await client.get(f"/api/v1/environments/{environment_id}/cloudflare-traffic-stats")

        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["hostname"] == "app.example.com"
        assert body["totalRequests"] == 42
        assert body["totalBytes"] == 1024
        assert fake_client.calls[0]["hostname"] == "app.example.com"
        assert fake_client.calls[0]["zone_id"] == "z1"

        del app.dependency_overrides[get_cloudflare_client]
