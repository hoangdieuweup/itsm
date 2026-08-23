"""Integration tests for app.modules.observability.router — real Postgres via
testcontainers. Mirrors tests/cloudflare/test_router.py's exact helper shape
(_login_with_permissions, real HTTP project/environment creation)."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.observability.config import observability_settings
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


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
            permissions=[("environment", "update"), ("environment", "read")],
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
            client, engine, permissions=[("environment", "read")], email="viewer2@x.com"
        )

        response = await client.get(f"/api/v1/environments/{environment_id}/loki-config")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "loki_config_not_found"

    async def test_rejects_duplicate_config(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("environment", "update"), ("environment", "read")],
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
            permissions=[("environment", "update"), ("environment", "read")],
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
            client, engine, permissions=[("environment", "read")], email="reader@x.com"
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
