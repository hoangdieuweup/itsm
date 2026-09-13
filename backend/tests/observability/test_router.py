"""Integration tests for app.modules.observability.router — real Postgres via
testcontainers. Mirrors tests/cloudflare/test_router.py's exact helper shape
(_login_with_permissions, real HTTP project/environment creation)."""

import json
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.crypto import FernetCodec
from app.core.security import JwtCodec
from app.integrations.cloudflare.dependencies import get_cloudflare_client
from app.integrations.cloudflare.schemas import ZoneOption
from app.integrations.loki.dependencies import get_loki_client
from app.integrations.loki.schemas import LokiLogEntry
from app.main import app
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.models import CloudflareAccount
from app.modules.observability.config import observability_settings
from app.modules.projects.models import Environment, ProjectMember
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User

_TEST_FERNET_KEY = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="


@pytest.fixture(autouse=True)
def _cloudflare_fernet_key_for_alert_rules(monkeypatch) -> None:
    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", _TEST_FERNET_KEY)


@pytest.fixture(autouse=True)
def _observability_fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(observability_settings, "FERNET_KEY", "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s=")


async def _login_with_permissions(
    client: AsyncClient,
    engine: AsyncEngine,
    *,
    permissions: list[tuple[str, str]],
    email: str = "actor@example.com",
) -> UUID:
    """Mirrors tests/cloudflare/test_router.py's helper of the same name and shape."""
    async with engine.begin() as conn:
        user_result = await conn.execute(
            insert(User).values(
                email=email,
                name=email,
                status="active",
                external_user_id=f"dx-{email}",
                employee_code=None,
                email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]
        role_result = await conn.execute(insert(Role).values(name=f"role-{email}", is_system=False))
        role_id = role_result.inserted_primary_key[0]
        for resource, action in permissions:
            existing = await conn.execute(
                select(Permission.id).where(Permission.resource == resource, Permission.action == action)
            )
            permission_id = existing.scalar_one_or_none()
            if permission_id is None:
                perm_result = await conn.execute(
                    insert(Permission).values(resource=resource, action=action, description_key="x")
                )
                permission_id = perm_result.inserted_primary_key[0]
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))
        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": f"test-jti-{email}"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


async def _make_environment(client: AsyncClient, engine: AsyncEngine) -> str:
    """Login with enough permissions to create a project + environment via
    the real HTTP API, mirroring _bind_environment's setup half."""
    await _login_with_permissions(
        client,
        engine,
        permissions=[("project", "create"), ("environment", "create"), ("environment", "read")],
    )
    project_resp = await client.post("/api/v1/projects", json={"name": "Site"})
    project_id = project_resp.json()["data"]["id"]
    env_resp = await client.post(
        f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "Dev"}
    )
    return env_resp.json()["data"]["id"]


async def _login_as_bare_project_member(
    client: AsyncClient, engine: AsyncEngine, *, environment_id: str, email: str
) -> UUID:
    """Log in a user who is a REAL member of the environment's project and
    holds no permission at all.

    project:manage_all cannot express "denied" any more — it grants the scoped
    surface. Plain membership is what isolates one atom."""
    user_id = await _login_with_permissions(client, engine, permissions=[], email=email)
    async with engine.begin() as conn:
        project_id = await conn.scalar(
            select(Environment.project_id).where(Environment.id == UUID(environment_id))
        )
        await conn.execute(insert(ProjectMember).values(project_id=project_id, user_id=user_id))
    return user_id


class TestCreateLokiConfig:
    async def test_requires_environment_update_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client, engine, permissions=[("environment", "read")], email="viewer@x.com"
        )

        response = await client.post(
            f"/api/v1/environments/{environment_id}/loki-config",
            json={
                "endpointUrl": "http://loki:3100",
                "tenantId": None,
                "authType": "none",
                "credential": None,
                "defaultQuery": "",
                "defaultRangeMinutes": 60,
            },
        )
        assert response.status_code == 403

    async def test_create_then_get(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project_loki_config", "manage"),
                ("project_loki_config", "read"),
                ("project", "manage_all"),
            ],
            email="admin@x.com",
        )

        create_response = await client.post(
            f"/api/v1/environments/{environment_id}/loki-config",
            json={
                "endpointUrl": "http://loki:3100",
                "tenantId": None,
                "authType": "none",
                "credential": None,
                "defaultQuery": "{}",
                "defaultRangeMinutes": 60,
            },
        )
        assert create_response.status_code == 200, create_response.text

        get_response = await client.get(f"/api/v1/environments/{environment_id}/loki-config")
        assert get_response.status_code == 200
        body = get_response.json()["data"]
        assert body["endpointUrl"] == "http://loki:3100"
        assert "credential" not in body
        assert body["hasCredential"] is False

    async def test_get_404s_when_unconfigured(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project_loki_config", "read"), ("project", "manage_all")],
            email="viewer2@x.com",
        )

        response = await client.get(f"/api/v1/environments/{environment_id}/loki-config")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "loki_config_not_found"

    async def test_rejects_duplicate_config(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project_loki_config", "manage"), ("project", "manage_all")],
            email="admin2@x.com",
        )
        payload = {
            "endpointUrl": "http://loki:3100",
            "tenantId": None,
            "authType": "none",
            "credential": None,
            "defaultQuery": "",
            "defaultRangeMinutes": 60,
        }
        first = await client.post(f"/api/v1/environments/{environment_id}/loki-config", json=payload)
        assert first.status_code == 200

        second = await client.post(f"/api/v1/environments/{environment_id}/loki-config", json=payload)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "loki_config_already_exists"


class TestUpdateAndDeleteLokiConfig:
    async def test_update_requires_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("environment", "update"), ("environment", "read")],
            email="admin3@x.com",
        )
        await client.post(
            f"/api/v1/environments/{environment_id}/loki-config",
            json={
                "endpointUrl": "http://loki:3100",
                "tenantId": None,
                "authType": "none",
                "credential": None,
                "defaultQuery": "",
                "defaultRangeMinutes": 60,
            },
        )

        await _login_with_permissions(
            client, engine, permissions=[("environment", "read")], email="viewer3@x.com"
        )
        response = await client.patch(
            f"/api/v1/environments/{environment_id}/loki-config", json={"defaultRangeMinutes": 120}
        )
        assert response.status_code == 403

    async def test_update_then_delete(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project_loki_config", "manage"),
                ("project_loki_config", "read"),
                ("project", "manage_all"),
            ],
            email="admin4@x.com",
        )
        await client.post(
            f"/api/v1/environments/{environment_id}/loki-config",
            json={
                "endpointUrl": "http://loki:3100",
                "tenantId": None,
                "authType": "none",
                "credential": None,
                "defaultQuery": "",
                "defaultRangeMinutes": 60,
            },
        )

        update_response = await client.patch(
            f"/api/v1/environments/{environment_id}/loki-config", json={"defaultRangeMinutes": 120}
        )
        assert update_response.status_code == 200
        assert update_response.json()["data"]["defaultRangeMinutes"] == 120

        delete_response = await client.delete(f"/api/v1/environments/{environment_id}/loki-config")
        assert delete_response.status_code == 200

        get_response = await client.get(f"/api/v1/environments/{environment_id}/loki-config")
        assert get_response.status_code == 404


class TestRunLogQuery:
    async def test_requires_environment_read_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(client, engine, permissions=[], email="noperm@x.com")

        response = await client.post(
            f"/api/v1/environments/{environment_id}/loki-config/query",
            json={
                "query": "{}",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T01:00:00Z",
                "limit": 100,
            },
        )
        assert response.status_code == 403

    async def test_404s_when_unconfigured(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project_loki_config", "read"), ("project", "manage_all")],
            email="reader@x.com",
        )

        response = await client.post(
            f"/api/v1/environments/{environment_id}/loki-config/query",
            json={
                "query": "{}",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-01T01:00:00Z",
                "limit": 100,
            },
        )
        assert response.status_code == 404


class TestStreamLogTail:
    async def test_requires_environment_read_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(client, engine, permissions=[], email="notail@x.com")

        response = await client.get(f"/api/v1/environments/{environment_id}/loki-config/tail?query=%7B%7D")
        assert response.status_code == 403

    async def test_404s_when_unconfigured(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project_loki_config", "read"), ("project", "manage_all")],
            email="tailreader@x.com",
        )

        response = await client.get(f"/api/v1/environments/{environment_id}/loki-config/tail?query=%7B%7D")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "loki_config_not_found"

    async def test_streams_entries_as_sse_events(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project_loki_config", "manage"),
                ("project_loki_config", "read"),
                ("project", "manage_all"),
            ],
            email="tailadmin@x.com",
        )
        await client.post(
            f"/api/v1/environments/{environment_id}/loki-config",
            json={
                "endpointUrl": "http://loki:3100",
                "tenantId": None,
                "authType": "none",
                "credential": None,
                "defaultQuery": "",
                "defaultRangeMinutes": 60,
            },
        )

        class FakeTailLokiClient:
            async def tail(self, **kwargs):
                yield LokiLogEntry(timestamp="1", line="hello", labels={})

        app.dependency_overrides[get_loki_client] = lambda: FakeTailLokiClient()

        try:
            async with client.stream(
                "GET", f"/api/v1/environments/{environment_id}/loki-config/tail?query=%7B%7D"
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                assert response.headers.get("x-accel-buffering") == "no"
                body_lines: list[str] = []
                async for line in response.aiter_lines():
                    body_lines.append(line)
                    if len(body_lines) > 3:
                        break
        finally:
            del app.dependency_overrides[get_loki_client]

        data_lines = [line for line in body_lines if line.startswith("data:")]
        assert len(data_lines) >= 1
        payload = json.loads(data_lines[0][len("data:") :].strip())
        assert payload["success"] is True
        assert payload["data"]["line"] == "hello"


class FakeCloudflareClientForAlerting:
    """Overrides the real CloudflareClient for observability's router tests —
    supports account creation (test_connection), zone binding (list_zones),
    and the alerting flow (create_webhook_destination/create_policy/
    update_policy/delete_policy)."""

    def __init__(self, policy_id: str = "policy-789", webhook_destination_id: str = "wh-123") -> None:
        self._policy_id = policy_id
        self._webhook_destination_id = webhook_destination_id
        self.created_policies: list[dict] = []
        self.deleted_policy_ids: list[str] = []

    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        pass

    async def list_zones(self, *, cf_account_id: str, api_token: str):
        return [ZoneOption(id="z1", name="example.com")]

    async def list_available_alerts(self, **kwargs):
        return [{"type": "advanced_ddos_attack_l4_alert"}]

    async def create_webhook_destination(self, **kwargs) -> str:
        return self._webhook_destination_id

    async def create_policy(self, **kwargs) -> str:
        self.created_policies.append(kwargs)
        return self._policy_id

    async def update_policy(self, **kwargs) -> None:
        pass

    async def delete_policy(self, *, cf_account_id, api_token, policy_id) -> None:
        self.deleted_policy_ids.append(policy_id)


async def _bind_environment(client: AsyncClient, engine: AsyncEngine, *, cf_client) -> tuple[str, str]:
    """Login with manage+view, create an account (creator becomes OWNER),
    create a project + environment, bind them. Returns (environment_id, account_id)."""
    app.dependency_overrides[get_cloudflare_client] = lambda: cf_client
    await _login_with_permissions(
        client,
        engine,
        permissions=[
            ("cloudflare_account", "create"),
            ("cloudflare_account", "read"),
            ("cloudflare_config", "manage"),
            ("alert_rule", "read"),
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
        f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "Dev"}
    )
    environment_id = env_resp.json()["data"]["id"]

    bind_resp = await client.post(
        "/api/v1/cloudflare-configs",
        json={"environmentId": environment_id, "cloudflareAccountId": account_id, "zoneId": "z1"},
    )
    assert bind_resp.status_code == 200, bind_resp.text
    return environment_id, account_id


class TestCloudflareWebhookAuth:
    async def test_wrong_secret_returns_401_and_creates_nothing(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        account_id = uuid4()
        response = await client.post(
            f"/api/v1/webhooks/cloudflare-alert/{account_id}",
            json={"policy_id": "p", "alert_event": "ALERT_STATE_EVENT_START"},
            headers={"cf-webhook-auth": "wrong-secret"},
        )
        assert response.status_code == 401

    async def test_correct_secret_returns_200_and_creates_incident(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        cf_client = FakeCloudflareClientForAlerting()
        environment_id, account_id = await _bind_environment(client, engine, cf_client=cf_client)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project_alert_rule", "create"), ("project", "manage_all")],
            email="alertadmin@x.com",
        )
        create_resp = await client.post(
            f"/api/v1/environments/{environment_id}/alert-rules",
            json={
                "name": "DDoS",
                "source": "CLOUDFLARE_NATIVE",
                "cfAlertType": "advanced_ddos_attack_l4_alert",
                "condition": None,
                "severity": "HIGH",
                "channelIds": [],
            },
        )
        assert create_resp.status_code == 200, create_resp.text

        async with engine.begin() as conn:
            result = await conn.execute(
                select(CloudflareAccount.webhook_secret_ciphertext).where(
                    CloudflareAccount.id == UUID(account_id)
                )
            )
            ciphertext = result.scalar_one()
        webhook_secret = FernetCodec.decrypt(ciphertext, key=_TEST_FERNET_KEY)

        del app.dependency_overrides[get_cloudflare_client]

        wrong_resp = await client.post(
            f"/api/v1/webhooks/cloudflare-alert/{account_id}",
            json={
                "policy_id": "policy-789",
                "text": "DDoS attack detected",
                "alert_type": "advanced_ddos_attack_l4_alert",
                "alert_correlation_id": "corr-1",
                "alert_event": "ALERT_STATE_EVENT_START",
            },
            headers={"cf-webhook-auth": "wrong-secret"},
        )
        assert wrong_resp.status_code == 401

        webhook_resp = await client.post(
            f"/api/v1/webhooks/cloudflare-alert/{account_id}",
            json={
                "policy_id": "policy-789",
                "text": "DDoS attack detected",
                "alert_type": "advanced_ddos_attack_l4_alert",
                "alert_correlation_id": "corr-1",
                "alert_event": "ALERT_STATE_EVENT_START",
            },
            headers={"cf-webhook-auth": webhook_secret},
        )
        assert webhook_resp.status_code == 200, webhook_resp.text


class TestLokiWebhookAuth:
    async def test_wrong_bearer_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/webhooks/loki-alert", json={"alerts": []}, headers={"Authorization": "Bearer wrong"}
        )
        assert response.status_code == 401

    async def test_correct_bearer_returns_200(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr(observability_settings, "LOKI_WEBHOOK_SECRET", "real-secret")
        response = await client.post(
            "/api/v1/webhooks/loki-alert",
            json={"alerts": []},
            headers={"Authorization": "Bearer real-secret"},
        )
        assert response.status_code == 200


class TestAlertRuleRoutes:
    async def test_create_requires_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        cf_client = FakeCloudflareClientForAlerting()
        environment_id, _account_id = await _bind_environment(client, engine, cf_client=cf_client)
        await _login_with_permissions(client, engine, permissions=[], email="noperm@x.com")

        response = await client.post(
            f"/api/v1/environments/{environment_id}/alert-rules",
            json={
                "name": "DDoS",
                "source": "CLOUDFLARE_NATIVE",
                "cfAlertType": "advanced_ddos_attack_l4_alert",
                "condition": None,
                "severity": "HIGH",
                "channelIds": [],
            },
        )
        assert response.status_code == 403
        del app.dependency_overrides[get_cloudflare_client]

    async def test_full_crud_cycle(self, client: AsyncClient, engine: AsyncEngine) -> None:
        cf_client = FakeCloudflareClientForAlerting()
        environment_id, _account_id = await _bind_environment(client, engine, cf_client=cf_client)
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project_alert_rule", "create"),
                ("project_alert_rule", "read"),
                ("project_alert_rule", "update"),
                ("project_alert_rule", "delete"),
                ("project", "manage_all"),
            ],
            email="alertfull@x.com",
        )

        create_resp = await client.post(
            f"/api/v1/environments/{environment_id}/alert-rules",
            json={
                "name": "DDoS",
                "source": "CLOUDFLARE_NATIVE",
                "cfAlertType": "advanced_ddos_attack_l4_alert",
                "condition": None,
                "severity": "HIGH",
                "channelIds": [],
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        alert_rule_id = create_resp.json()["data"]["id"]
        assert create_resp.json()["data"]["cfPolicyId"] == "policy-789"

        list_resp = await client.get(f"/api/v1/environments/{environment_id}/alert-rules")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["data"]) == 1

        update_resp = await client.patch(f"/api/v1/alert-rules/{alert_rule_id}", json={"isActive": False})
        assert update_resp.status_code == 200
        assert update_resp.json()["data"]["isActive"] is False

        delete_resp = await client.delete(f"/api/v1/alert-rules/{alert_rule_id}")
        assert delete_resp.status_code == 200
        assert cf_client.deleted_policy_ids == ["policy-789"]

        del app.dependency_overrides[get_cloudflare_client]

    async def test_available_alerts_requires_account_access(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        cf_client = FakeCloudflareClientForAlerting()
        _environment_id, account_id = await _bind_environment(client, engine, cf_client=cf_client)
        await _login_with_permissions(
            client, engine, permissions=[("alert_rule", "read")], email="noaccountaccess@x.com"
        )

        response = await client.get(f"/api/v1/cloudflare-accounts/{account_id}/available-alerts")
        assert response.status_code == 403
        del app.dependency_overrides[get_cloudflare_client]

    async def test_available_alerts_returns_options_for_the_bound_account(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """Regression test for the account_id/environment_id mismatch bug —
        this endpoint's path param is a Cloudflare account id, and the
        creator from _bind_environment is that account's OWNER manager, so
        this proves the full router -> service -> facade -> client chain
        actually resolves and returns data instead of always 404ing."""
        cf_client = FakeCloudflareClientForAlerting()
        _environment_id, account_id = await _bind_environment(client, engine, cf_client=cf_client)

        response = await client.get(f"/api/v1/cloudflare-accounts/{account_id}/available-alerts")

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data == [
            {"alertType": "advanced_ddos_attack_l4_alert", "displayName": "Advanced Ddos Attack L4 Alert"}
        ]
        del app.dependency_overrides[get_cloudflare_client]


class TestIncidentRoutes:
    async def test_manual_create_ack_resolve_flow(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project_incident", "create"),
                ("project_incident", "read"),
                ("incident", "read"),
                ("project_incident", "acknowledge"),
                ("project_incident", "resolve"),
                ("project", "manage_all"),
            ],
            email="incidentfull@x.com",
        )

        create_resp = await client.post(
            "/api/v1/incidents",
            json={
                "environmentId": environment_id,
                "category": "TRAFFIC",
                "severity": "MEDIUM",
                "title": "Manually filed",
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        incident_id = create_resp.json()["data"]["id"]
        assert create_resp.json()["data"]["status"] == "OPEN"

        get_resp = await client.get(f"/api/v1/incidents/{incident_id}")
        assert get_resp.status_code == 200

        list_resp = await client.get("/api/v1/incidents")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["data"]) >= 1

        ack_resp = await client.post(f"/api/v1/incidents/{incident_id}/acknowledge")
        assert ack_resp.status_code == 200
        assert ack_resp.json()["data"]["status"] == "ACKNOWLEDGED"

        resolve_resp = await client.post(f"/api/v1/incidents/{incident_id}/resolve")
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["data"]["status"] == "RESOLVED"

    async def test_acknowledge_requires_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        """A nonexistent incident 404s regardless of permission —
        require_project_permission_for_incident resolves the incident (and
        its project membership) before checking the acknowledge atom, same
        precedent as require_project_permission_for_environment. So this
        test proves the permission boundary against a REAL incident the
        caller is a project member of but lacks incident:acknowledge for."""
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project_incident", "create"), ("project", "manage_all")],
            email="incidentcreator@x.com",
        )
        create_resp = await client.post(
            "/api/v1/incidents",
            json={
                "environmentId": environment_id,
                "category": "TRAFFIC",
                "severity": "MEDIUM",
                "title": "X",
            },
        )
        incident_id = create_resp.json()["data"]["id"]

        await _login_as_bare_project_member(
            client, engine, environment_id=environment_id, email="noincidentperm@x.com"
        )
        response = await client.post(f"/api/v1/incidents/{incident_id}/acknowledge")
        assert response.status_code == 403

    async def test_resolve_requires_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project_incident", "create"), ("project", "manage_all")],
            email="incidentcreator2@x.com",
        )
        create_resp = await client.post(
            "/api/v1/incidents",
            json={
                "environmentId": environment_id,
                "category": "TRAFFIC",
                "severity": "MEDIUM",
                "title": "X",
            },
        )
        incident_id = create_resp.json()["data"]["id"]

        await _login_as_bare_project_member(
            client, engine, environment_id=environment_id, email="noresolveperm@x.com"
        )
        response = await client.post(f"/api/v1/incidents/{incident_id}/resolve")
        assert response.status_code == 403

    async def test_manage_all_holder_acknowledges_without_membership_or_project_role(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """Not a member, no project role, yet reaches a scoped route —
        manage_all now carries the scoped surface."""
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project_incident", "create"), ("project", "manage_all")],
            email="incidentcreator3@x.com",
        )
        create_resp = await client.post(
            "/api/v1/incidents",
            json={
                "environmentId": environment_id,
                "category": "TRAFFIC",
                "severity": "MEDIUM",
                "title": "X",
            },
        )
        incident_id = create_resp.json()["data"]["id"]

        await _login_with_permissions(
            client,
            engine,
            permissions=[("project", "manage_all")],
            email="manageallonly@x.com",
        )
        response = await client.post(f"/api/v1/incidents/{incident_id}/acknowledge")
        assert response.status_code == 200, response.text

    async def test_returns_404_for_unknown_incident_even_without_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """Explicit proof of the new, intentional behavior: resource
        existence is resolved before the permission check, so an unknown
        incident_id 404s regardless of the caller's permissions."""
        await _login_with_permissions(client, engine, permissions=[], email="nopermatall@x.com")
        response = await client.post(f"/api/v1/incidents/{uuid4()}/acknowledge")
        assert response.status_code == 404

    async def test_create_requires_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(client, engine, permissions=[], email="nocreateperm@x.com")
        response = await client.post(
            "/api/v1/incidents",
            json={
                "environmentId": environment_id,
                "category": "TRAFFIC",
                "severity": "MEDIUM",
                "title": "X",
            },
        )
        assert response.status_code == 403
