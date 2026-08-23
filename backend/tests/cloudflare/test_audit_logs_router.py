"""Integration tests for the new GET /environments/{id}/cloudflare-audit-logs
route added to app.modules.cloudflare.router in Phase 6. Split into its own
file to keep this addition self-contained and easy to find, while reusing
test_router.py's exact fixtures/helpers via import."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.integrations.cloudflare.dependencies import get_cloudflare_client
from app.integrations.cloudflare.schemas import ZoneOption
from app.main import app
from app.modules.cloudflare.config import cloudflare_settings
from tests.cloudflare.test_router import FakeCloudflareClient, _bind_environment, _login_with_permissions


@pytest.fixture(autouse=True)
def _cloudflare_fernet_key(monkeypatch) -> None:
    """_bind_environment creates a real Cloudflare account, which really
    encrypts its token — needs a real 32-byte Fernet key, same as
    test_router.py's own fixture of this name."""
    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s=")


class FakeAuditLogsClient(FakeCloudflareClient):
    def __init__(self, entries: list | None = None) -> None:
        super().__init__(zones=[ZoneOption(id="z1", name="example.com")])
        self._entries = entries if entries is not None else []
        self.calls: list[dict] = []

    async def get_account_audit_logs(self, *, cf_account_id, api_token, zone_name, since, before):
        self.calls.append({"cf_account_id": cf_account_id, "zone_name": zone_name})
        return self._entries


class TestListCloudflareAuditLogsRoute:
    async def test_requires_view_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id, _account_id, _owner_id = await _bind_environment(
            client, engine, cf_client=FakeAuditLogsClient()
        )
        await _login_with_permissions(client, engine, permissions=[], email="noperm@x.com")

        response = await client.get(f"/api/v1/environments/{environment_id}/cloudflare-audit-logs")
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

        response = await client.get(f"/api/v1/environments/{environment_id}/cloudflare-audit-logs")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "cloudflare_config_not_found"

    async def test_returns_entries_filtered_to_bound_zone(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        fake_client = FakeAuditLogsClient(
            entries=[
                {
                    "id": "log-1",
                    "when": "2026-01-01T00:00:00Z",
                    "actorEmail": "a@b.com",
                    "actorIp": "1.2.3.4",
                    "actionType": "update",
                    "resourceType": "dns_record",
                    "resourceProduct": "dns",
                    "newValue": "1.2.3.4",
                }
            ]
        )
        environment_id, _account_id, _owner_id = await _bind_environment(
            client, engine, cf_client=fake_client
        )

        response = await client.get(f"/api/v1/environments/{environment_id}/cloudflare-audit-logs")

        assert response.status_code == 200
        body = response.json()["data"]
        assert len(body) == 1
        assert body[0]["id"] == "log-1"
        assert fake_client.calls[0]["zone_name"] == "example.com"

        del app.dependency_overrides[get_cloudflare_client]
