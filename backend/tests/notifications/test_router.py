"""Integration tests for app.modules.notifications.router — real Postgres via
testcontainers. Mirrors tests/observability/test_router.py's exact helper shape."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.integrations.telegram.dependencies import get_telegram_client
from app.main import app
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.notifications.config import notifications_settings
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch) -> None:
    monkeypatch.setattr(notifications_settings, "FERNET_KEY", "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s=")


async def _login_with_permissions(
    client: AsyncClient,
    engine: AsyncEngine,
    *,
    permissions: list[tuple[str, str]],
    email: str = "actor@example.com",
) -> UUID:
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


async def _make_project(client: AsyncClient, engine: AsyncEngine) -> str:
    await _login_with_permissions(client, engine, permissions=[("project", "create")])
    resp = await client.post("/api/v1/projects", json={"name": "Site"})
    return resp.json()["data"]["id"]


class TestCreateAndListChannels:
    async def test_requires_create_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(client, engine, permissions=[], email="nope@x.com")

        response = await client.post(
            "/api/v1/notification-channels",
            json={
                "projectId": project_id,
                "type": "email",
                "name": "Team",
                "config": {"recipients": ["a@b.com"]},
            },
        )
        assert response.status_code == 403

    async def test_create_then_list(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("notification_channel", "create"), ("notification_channel", "read")],
            email="admin@x.com",
        )

        create_response = await client.post(
            "/api/v1/notification-channels",
            json={
                "projectId": project_id,
                "type": "telegram",
                "name": "Ops",
                "config": {"bot_token": "tok", "chat_id": "1"},
            },
        )
        assert create_response.status_code == 200, create_response.text
        body = create_response.json()["data"]
        assert "bot_token" not in body["config"]
        assert body["config"]["has_bot_token"] is True

        list_response = await client.get(f"/api/v1/notification-channels?projectId={project_id}")
        assert list_response.status_code == 200
        assert len(list_response.json()["data"]) == 1

    async def test_rejects_invalid_config(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(
            client, engine, permissions=[("notification_channel", "create")], email="badconfig@x.com"
        )

        response = await client.post(
            "/api/v1/notification-channels",
            json={"projectId": project_id, "type": "telegram", "name": "Ops", "config": {}},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "notification_channel_invalid_config"


class TestUpdateAndDeleteChannel:
    async def test_update_requires_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("notification_channel", "create"), ("notification_channel", "read")],
            email="creator@x.com",
        )
        create_response = await client.post(
            "/api/v1/notification-channels",
            json={
                "projectId": project_id,
                "type": "email",
                "name": "Team",
                "config": {"recipients": ["a@b.com"]},
            },
        )
        channel_id = create_response.json()["data"]["id"]

        await _login_with_permissions(client, engine, permissions=[], email="noupdate@x.com")
        response = await client.patch(f"/api/v1/notification-channels/{channel_id}", json={"name": "Renamed"})
        assert response.status_code == 403

    async def test_update_then_delete(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("notification_channel", "create"),
                ("notification_channel", "read"),
                ("notification_channel", "update"),
                ("notification_channel", "delete"),
            ],
            email="full@x.com",
        )
        create_response = await client.post(
            "/api/v1/notification-channels",
            json={
                "projectId": project_id,
                "type": "email",
                "name": "Team",
                "config": {"recipients": ["a@b.com"]},
            },
        )
        channel_id = create_response.json()["data"]["id"]

        update_response = await client.patch(
            f"/api/v1/notification-channels/{channel_id}", json={"name": "Renamed"}
        )
        assert update_response.status_code == 200
        assert update_response.json()["data"]["name"] == "Renamed"

        delete_response = await client.delete(f"/api/v1/notification-channels/{channel_id}")
        assert delete_response.status_code == 200

        get_response = await client.get(f"/api/v1/notification-channels/{channel_id}")
        assert get_response.status_code == 404


class TestTestSendChannel:
    async def test_requires_update_permission_not_just_read(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("notification_channel", "create"), ("notification_channel", "read")],
            email="reader@x.com",
        )
        create_response = await client.post(
            "/api/v1/notification-channels",
            json={
                "projectId": project_id,
                "type": "telegram",
                "name": "Ops",
                "config": {"bot_token": "tok", "chat_id": "1"},
            },
        )
        channel_id = create_response.json()["data"]["id"]

        response = await client.post(f"/api/v1/notification-channels/{channel_id}/test-send", json={})
        assert response.status_code == 403

    async def test_dispatches_to_telegram_client(self, client: AsyncClient, engine: AsyncEngine) -> None:
        project_id = await _make_project(client, engine)
        await _login_with_permissions(
            client,
            engine,
            permissions=[("notification_channel", "create"), ("notification_channel", "update")],
            email="sender@x.com",
        )
        create_response = await client.post(
            "/api/v1/notification-channels",
            json={
                "projectId": project_id,
                "type": "telegram",
                "name": "Ops",
                "config": {"bot_token": "tok", "chat_id": "1"},
            },
        )
        channel_id = create_response.json()["data"]["id"]

        calls: list[dict] = []

        class FakeTelegramClient:
            async def send_message(self, **kwargs):
                calls.append(kwargs)

        app.dependency_overrides[get_telegram_client] = lambda: FakeTelegramClient()
        try:
            response = await client.post(f"/api/v1/notification-channels/{channel_id}/test-send", json={})
            assert response.status_code == 200, response.text
        finally:
            del app.dependency_overrides[get_telegram_client]

        assert calls[0]["bot_token"] == "tok"
        assert calls[0]["chat_id"] == "1"
