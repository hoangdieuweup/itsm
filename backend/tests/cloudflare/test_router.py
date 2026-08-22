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
from app.modules.cloudflare.schemas import ZoneOption
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

    def __init__(
        self,
        raises: Exception | None = None,
        zones: list | None = None,
        create_record_id: str = "rec-fake",
    ) -> None:
        self._raises = raises
        self._zones = zones or []
        self._create_record_id = create_record_id
        self.deleted_record_ids: list[str] = []

    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        if self._raises is not None:
            raise self._raises

    async def list_zones(self, *, cf_account_id: str, api_token: str):
        return self._zones

    async def create_dns_record(self, **kwargs) -> str:
        return self._create_record_id

    async def update_dns_record(self, **kwargs) -> None:
        pass

    async def delete_dns_record(self, *, zone_id, cf_record_id, api_token) -> None:
        self.deleted_record_ids.append(cf_record_id)


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


async def _bind_environment(
    client: AsyncClient, engine: AsyncEngine, *, cf_client: FakeCloudflareClient
) -> tuple[str, str, UUID]:
    """Full setup: login with manage+view, create an account (creator becomes
    its OWNER), create a project + environment, bind them.
    Returns (environment_id, account_id, owner_user_id)."""
    app.dependency_overrides[get_cloudflare_client] = lambda: cf_client
    owner_id = await _login_with_permissions(
        client,
        engine,
        permissions=[
            ("cloudflare_account", "manage"),
            ("cloudflare_account", "view"),
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
    return environment_id, account_id, owner_id


class TestCreateCloudflareConfig:
    async def test_reads_account_id_from_body_not_query_param(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """Decision #1's regression test: if cloudflare_account_id were
        accidentally resolved as a query param (the FastAPI misresolution
        bug the Phase 4 pressure-test caught), this POST — sent with only a
        JSON body, no query string — would either 422 (FastAPI treating
        account_id as a required query param) or silently check access
        against nothing. A 200 with the config's cloudflare_account_id
        matching the body proves the fix."""
        cf_client = FakeCloudflareClient(zones=[ZoneOption(id="z1", name="example.com")])
        app.dependency_overrides[get_cloudflare_client] = lambda: cf_client
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("cloudflare_account", "manage"),
                ("cloudflare_account", "view"),
                ("project", "create"),
                ("environment", "create"),
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

        response = await client.post(
            "/api/v1/cloudflare-configs",
            json={"environmentId": environment_id, "cloudflareAccountId": account_id, "zoneId": "z1"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["data"]["cloudflareAccountId"] == account_id
        assert response.json()["data"]["zoneName"] == "example.com"

        del app.dependency_overrides[get_cloudflare_client]

    async def test_rejects_cross_account_zone_spoofing(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """Decision #5's regression test: a zone_id that only belongs to a
        DIFFERENT account than the one named in the request body must be
        rejected — this is what blocks a real cross-account spoofing vector,
        not just staleness."""
        cf_client = FakeCloudflareClient(zones=[ZoneOption(id="owned-by-account-a", name="a.com")])
        app.dependency_overrides[get_cloudflare_client] = lambda: cf_client
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("cloudflare_account", "manage"),
                ("cloudflare_account", "view"),
                ("project", "create"),
                ("environment", "create"),
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

        response = await client.post(
            "/api/v1/cloudflare-configs",
            json={
                "environmentId": environment_id,
                "cloudflareAccountId": account_id,
                "zoneId": "belongs-to-a-different-account",
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cloudflare_zone_not_owned_by_account"

        del app.dependency_overrides[get_cloudflare_client]


class TestDnsRecordFullDemoScript:
    async def test_bind_create_delete_and_permission_boundary(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """The Phase 4 acceptance demo, verbatim: bind an environment to an
        account+zone -> create an A record -> row has managed_by=SYSTEM and a
        real cf_record_id -> delete it -> a sub-EDITOR user gets 403, no
        partial state either side."""
        cf_client = FakeCloudflareClient(
            zones=[ZoneOption(id="z1", name="example.com")], create_record_id="rec-real-123"
        )
        environment_id, account_id, owner_id = await _bind_environment(client, engine, cf_client=cf_client)

        create_resp = await client.post(
            f"/api/v1/environments/{environment_id}/dns-records",
            json={"recordType": "A", "name": "app", "content": "1.2.3.4", "proxied": True, "ttl": 1},
        )
        assert create_resp.status_code == 200, create_resp.text
        record = create_resp.json()["data"]
        assert record["managedBy"] == "system"
        assert record["cfRecordId"] == "rec-real-123"

        delete_resp = await client.delete(f"/api/v1/environments/{environment_id}/dns-records/{record['id']}")
        assert delete_resp.status_code == 200
        assert cf_client.deleted_record_ids == ["rec-real-123"]

        list_resp = await client.get(f"/api/v1/environments/{environment_id}/dns-records")
        assert list_resp.json()["data"] == []

        # A user who is only an EDITOR-below level (VIEWER) on the account
        # must be blocked from writing DNS records, with no partial state.
        viewer_id = await _login_with_permissions(
            client,
            engine,
            permissions=[("cloudflare_account", "manage"), ("cloudflare_account", "view")],
            email="viewer@example.com",
        )
        # Switch back to the account's OWNER (its creator) to assign the viewer.
        owner_token = JwtCodec.encode(
            {"sub": str(owner_id), "type": "access", "jti": "owner-reassign"},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, owner_token)
        assign_resp = await client.post(
            f"/api/v1/cloudflare-accounts/{account_id}/managers",
            json={"userId": str(viewer_id), "accessLevel": "viewer"},
        )
        assert assign_resp.status_code == 200, assign_resp.text

        viewer_token = JwtCodec.encode(
            {"sub": str(viewer_id), "type": "access", "jti": "viewer-write-attempt"},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, viewer_token)

        blocked_resp = await client.post(
            f"/api/v1/environments/{environment_id}/dns-records",
            json={"recordType": "A", "name": "blocked", "content": "9.9.9.9", "proxied": False, "ttl": 1},
        )
        assert blocked_resp.status_code == 403

        remaining_resp = await client.get(f"/api/v1/environments/{environment_id}/dns-records")
        assert remaining_resp.status_code == 200
        assert remaining_resp.json()["data"] == []

        del app.dependency_overrides[get_cloudflare_client]

    async def test_mx_record_requires_priority(self, client: AsyncClient, engine: AsyncEngine) -> None:
        cf_client = FakeCloudflareClient(zones=[ZoneOption(id="z1", name="example.com")])
        environment_id, _account_id, _owner_id = await _bind_environment(client, engine, cf_client=cf_client)

        response = await client.post(
            f"/api/v1/environments/{environment_id}/dns-records",
            json={
                "recordType": "MX",
                "name": "app",
                "content": "mail.example.com",
                "proxied": False,
                "ttl": 1,
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cloudflare_missing_dns_priority"

        del app.dependency_overrides[get_cloudflare_client]
