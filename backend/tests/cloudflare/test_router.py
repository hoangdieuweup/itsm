"""Integration tests for app.modules.cloudflare.router — real Postgres via
testcontainers, Cloudflare API calls faked via a dependency override."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.main import app
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.dependencies import get_cloudflare_client
from app.modules.cloudflare.exceptions import InvalidCloudflareToken
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


@pytest.fixture(autouse=True)
def _cloudflare_fernet_key(monkeypatch) -> None:
    """CreateCloudflareAccount really encrypts even with a faked
    CloudflareClient override — the module's default FERNET_KEY is "",
    which Fernet() rejects outright."""
    monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s=")


class FakeCloudflareClient:
    """Overrides the real CloudflareClient for the duration of one test —
    no test in this file makes a real network call."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises

    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        if self._raises is not None:
            raise self._raises


async def _login_with_permissions(
    client: AsyncClient,
    engine: AsyncEngine,
    *,
    permissions: list[tuple[str, str]],
    email: str = "actor@example.com",
) -> UUID:
    """Create a user with a fresh role granting exactly `permissions`, then
    authenticate `client` as them. Mirrors tests/audit/test_router.py's
    helper of the same name and shape — extended to be idempotent on the
    Permission row itself, since Layer-2 ACL tests routinely log in more
    than one user per test with an overlapping permission set (e.g. an
    OWNER and a VIEWER both needing `cloudflare_account:view`), which would
    otherwise violate the (resource, action) unique constraint on a second
    insert of the same tuple within one test."""
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


MANAGE_AND_VIEW = [("cloudflare_account", "manage"), ("cloudflare_account", "view")]


class TestCreateCloudflareAccount:
    async def test_creates_account_response_never_includes_token(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW)

        response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - Customer A", "cfAccountId": "cf-1", "apiToken": "real-token"},
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["label"] == "CF - Customer A"
        assert "apiToken" not in body
        assert "api_token" not in body

        del app.dependency_overrides[get_cloudflare_client]

    async def test_rejects_bad_token_with_no_row_persisted(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient(
            raises=InvalidCloudflareToken()
        )
        await _login_with_permissions(client, engine, permissions=[("cloudflare_account", "manage")])

        response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - Bad", "cfAccountId": "cf-2", "apiToken": "bad-token"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cloudflare_invalid_token"

        del app.dependency_overrides[get_cloudflare_client]

    async def test_requires_manage_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "X", "cfAccountId": "cf-3", "apiToken": "x"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"


class TestListCloudflareAccountsFiltering:
    async def test_user_with_no_relationship_sees_empty_list_not_403(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW, email="owner@example.com")
        await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - Owner's", "cfAccountId": "cf-1", "apiToken": "x"},
        )

        await _login_with_permissions(
            client, engine, permissions=[("cloudflare_account", "view")], email="outsider@example.com"
        )
        response = await client.get("/api/v1/cloudflare-accounts")

        assert response.status_code == 200
        assert response.json()["data"] == []

        del app.dependency_overrides[get_cloudflare_client]


class TestRevealTokenAccessLevel:
    async def test_viewer_manager_cannot_reveal_token(self, client: AsyncClient, engine: AsyncEngine) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        owner_id = await _login_with_permissions(
            client, engine, permissions=MANAGE_AND_VIEW, email="owner@example.com"
        )
        create_response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"},
        )
        account_id = create_response.json()["data"]["id"]

        # The viewer needs Layer-1 `manage` too, or reveal-token's Layer-1
        # require_permission("manage") check blocks them before Layer-2
        # (require_account_access(OWNER)) is ever reached — this test is
        # specifically about the Layer-2 block, so Layer-1 must pass first.
        viewer_id = await _login_with_permissions(
            client, engine, permissions=MANAGE_AND_VIEW, email="viewer@example.com"
        )
        # Re-authenticate as the owner (their own cookie was overwritten
        # above) so they, not the viewer, perform the assignment.
        token = JwtCodec.encode(
            {"sub": str(owner_id), "type": "access", "jti": "owner-again"},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
        assign_response = await client.post(
            f"/api/v1/cloudflare-accounts/{account_id}/managers",
            json={"userId": str(viewer_id), "accessLevel": "viewer"},
        )
        assert assign_response.status_code == 200

        # Switch back to the viewer and attempt to reveal the token.
        viewer_token = JwtCodec.encode(
            {"sub": str(viewer_id), "type": "access", "jti": "viewer-again"},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, viewer_token)

        response = await client.post(f"/api/v1/cloudflare-accounts/{account_id}/reveal-token")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "cloudflare_insufficient_account_access"

        del app.dependency_overrides[get_cloudflare_client]


class TestLastOwnerGuardViaRouter:
    async def test_delete_manager_blocked_for_last_owner(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        owner_id = await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW)
        create_response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"},
        )
        account_id = create_response.json()["data"]["id"]

        response = await client.delete(f"/api/v1/cloudflare-accounts/{account_id}/managers/{owner_id}")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "cloudflare_last_owner_removal_blocked"

        del app.dependency_overrides[get_cloudflare_client]

    async def test_downgrade_manager_blocked_for_last_owner(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        owner_id = await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW)
        create_response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"},
        )
        account_id = create_response.json()["data"]["id"]

        response = await client.patch(
            f"/api/v1/cloudflare-accounts/{account_id}/managers/{owner_id}",
            json={"accessLevel": "editor"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "cloudflare_last_owner_removal_blocked"

        del app.dependency_overrides[get_cloudflare_client]
