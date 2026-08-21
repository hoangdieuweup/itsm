"""Integration tests for app.modules.auth.router.

Real Postgres + real Redis (via the `client`/`cache_client` fixtures), fake
DX HTTP client only — no real network call ever reaches WeUpBook DX. This
covers what the unit tests in test_services.py deliberately can't: cookies,
redirects, the ApiResponse envelope, and the blacklist actually round
tripping through Redis end to end.
"""

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.integrations.dx_core.client import DxCoreClient, DxDepartment, DxUserProfile
from app.integrations.dx_core.dependencies import get_dx_core_client
from app.main import app
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.auth.models import User
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole


@dataclass
class _FakeDxTokenSet:
    access_token: str = "dx-access-token"
    refresh_token: str = "dx-refresh-token"
    expires_in: int = 3600
    scope: str = ""


class _FakeDxCoreClient:
    """Overrides only the network methods; PKCE/authorize-URL logic stays real
    (bound from the real DxCoreClient, which do no I/O — see their own markers)."""

    generate_pkce_pair = DxCoreClient.generate_pkce_pair
    build_authorize_url = DxCoreClient.build_authorize_url
    _redirect_uri = DxCoreClient._redirect_uri

    def __init__(self, profile: DxUserProfile) -> None:
        self._profile = profile
        self.revoked: list[str] = []

    async def exchange_code(self, code: str, code_verifier: str) -> _FakeDxTokenSet:
        return _FakeDxTokenSet()

    async def fetch_userinfo(self, access_token: str) -> DxUserProfile:
        return self._profile

    async def revoke(self, token: str) -> None:
        self.revoked.append(token)


def _profile(**overrides) -> DxUserProfile:
    defaults = {
        "sub": "dx-sub-router-1",
        "email": "carol@example.com",
        "name": "Carol",
        "department": DxDepartment(code="mkt", name="Marketing"),
        "roles": ["employee"],
        "employee_code": "E002",
        "email_verified": True,
    }
    defaults.update(overrides)
    return DxUserProfile(**defaults)


def _install_fake_dx_client(profile: DxUserProfile) -> _FakeDxCoreClient:
    fake = _FakeDxCoreClient(profile)
    app.dependency_overrides[get_dx_core_client] = lambda: fake
    return fake


async def _login_with_permissions(
    client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]
) -> int:
    """Seed a user with a role granting exactly `permissions`, and a valid
    session cookie for them — same pattern as tests/rbac/test_router.py's
    _login_as, duplicated here rather than shared since these are two
    different test suites for two different modules with no shared test-only
    module to own a common helper without creating a test-code coupling."""
    async with engine.begin() as conn:
        permission_ids = []
        for resource, action in permissions:
            result = await conn.execute(
                insert(Permission).values(resource=resource, action=action, description="x")
            )
            permission_ids.append(result.inserted_primary_key[0])
        role_result = await conn.execute(insert(Role).values(name="auth-test-role", is_system=False))
        role_id = role_result.inserted_primary_key[0]
        for permission_id in permission_ids:
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))
        user_result = await conn.execute(
            insert(User).values(
                email="permission-test@example.com",
                name="Permission Test",
                status="active",
                external_user_id="dx-permission-test",
                employee_code=None,
                email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]
        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": "auth-test-jti"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


async def _start_and_get_state(client: AsyncClient) -> str:
    response = await client.get("/api/v1/auth/oauth/dx/start")
    assert response.status_code == 302
    location = response.headers["location"]
    query = parse_qs(urlparse(location).query)
    assert query["client_id"] == ["local-test-client-id"]
    assert query["code_challenge_method"] == ["S256"]
    return query["state"][0]


class TestOAuthStart:
    async def test_redirects_to_dx_authorize_with_pkce_params(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/oauth/dx/start")

        assert response.status_code == 302
        location = urlparse(response.headers["location"])
        assert location.path == "/oauth2/authorize"
        query = parse_qs(location.query)
        assert query["response_type"] == ["code"]
        assert "state" in query
        assert "code_challenge" in query


class TestOAuthCallback:
    async def test_new_user_login_sets_session_cookies_and_redirects_to_frontend(
        self, client: AsyncClient
    ) -> None:
        _install_fake_dx_client(_profile())
        state = await _start_and_get_state(client)

        response = await client.get(
            "/api/v1/auth/oauth/dx/callback", params={"code": "auth-code", "state": state}
        )

        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:3000"
        cookie_names = {c for c in response.cookies}
        assert {AuthCookies.ACCESS_TOKEN, AuthCookies.REFRESH_TOKEN} <= cookie_names

    async def test_me_returns_the_signed_in_users_profile(self, client: AsyncClient) -> None:
        _install_fake_dx_client(_profile(email="dave@example.com", sub="dx-sub-router-2"))
        state = await _start_and_get_state(client)
        callback = await client.get(
            "/api/v1/auth/oauth/dx/callback", params={"code": "auth-code", "state": state}
        )
        client.cookies.update(callback.cookies)

        response = await client.get("/api/v1/auth/me")

        body = response.json()
        assert response.status_code == 200
        assert body["success"] is True
        assert body["data"]["user"]["email"] == "dave@example.com"
        assert body["data"]["roleName"] == "member"
        assert body["data"]["permissions"] == []

    async def test_denied_at_dx_redirects_with_sso_denied_error(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/oauth/dx/callback", params={"error": "access_denied"})

        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:3000/login?error=sso_denied"

    async def test_unknown_or_expired_state_redirects_with_sso_state_error(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/auth/oauth/dx/callback", params={"code": "auth-code", "state": "never-issued"}
        )

        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:3000/login?error=sso_state"

    async def test_state_is_single_use(self, client: AsyncClient) -> None:
        _install_fake_dx_client(_profile(email="erin@example.com", sub="dx-sub-router-3"))
        state = await _start_and_get_state(client)
        first = await client.get(
            "/api/v1/auth/oauth/dx/callback", params={"code": "auth-code", "state": state}
        )
        assert first.status_code == 302
        assert first.headers["location"] == "http://localhost:3000"

        second = await client.get(
            "/api/v1/auth/oauth/dx/callback", params={"code": "auth-code", "state": state}
        )

        assert second.headers["location"] == "http://localhost:3000/login?error=sso_state"


class TestMeWithoutSession:
    async def test_returns_401_envelope_when_no_cookie_present(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")

        body = response.json()
        assert response.status_code == 401
        assert body["success"] is False
        assert body["error"]["code"] == "auth_not_authenticated"


class TestListUsers:
    async def test_requires_user_read_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.get("/api/v1/auth/users")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_lists_users_with_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[("user", "read")])

        response = await client.get("/api/v1/auth/users")

        body = response.json()
        assert response.status_code == 200
        assert any(u["email"] == "permission-test@example.com" for u in body["data"]["items"])


class TestUpdateUserStatus:
    async def test_blocks_a_user(self, client: AsyncClient, engine: AsyncEngine) -> None:
        admin_id = await _login_with_permissions(client, engine, permissions=[("user", "update_status")])
        async with engine.begin() as conn:
            target = await conn.execute(
                insert(User).values(
                    email="target-block@example.com",
                    name="Target",
                    status="active",
                    external_user_id="dx-target-block",
                    employee_code=None,
                    email_confirmed=True,
                )
            )
            target_id = target.inserted_primary_key[0]

        response = await client.patch(f"/api/v1/auth/users/{target_id}/status", json={"status": "blocked"})

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["status"] == "blocked"
        assert target_id != admin_id  # sanity: didn't accidentally block the actor itself

    async def test_rejects_blocking_the_last_owner(self, client: AsyncClient, engine: AsyncEngine) -> None:
        actor_id = await _login_with_permissions(client, engine, permissions=[("user", "update_status")])
        async with engine.begin() as conn:
            owner_role_id = (await conn.execute(select(Role.id).where(Role.name == "owner"))).scalar_one()
            # conftest's _seed_default_roles creates "owner" with zero
            # permissions (unlike the real seed_rbac.py, which grants it
            # everything) — grant it user.update_status here so the actor's
            # switch to owner below doesn't itself 403 on the permission
            # check before ever reaching the bus-factor rule under test.
            update_status_permission_id = (
                await conn.execute(
                    select(Permission.id).where(
                        Permission.resource == "user", Permission.action == "update_status"
                    )
                )
            ).scalar_one()  # unique per (resource, action) — permissions_resource_key constraint
            await conn.execute(
                insert(RolePermission).values(
                    role_id=owner_role_id, permission_id=update_status_permission_id
                )
            )
            # UserRole.user_id is the primary key (one role per user) — this
            # UPDATE replaces the test-role grant _login_with_permissions made
            # with owner, same as rbac.services.assign_role.AssignRole.execute
            # would via an upsert.
            await conn.execute(
                update(UserRole).where(UserRole.user_id == actor_id).values(role_id=owner_role_id)
            )

        response = await client.patch(f"/api/v1/auth/users/{actor_id}/status", json={"status": "blocked"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "auth_cannot_block_last_owner"


class TestLogout:
    async def test_logout_clears_cookies_and_blacklists_the_session(self, client: AsyncClient) -> None:
        fake = _install_fake_dx_client(_profile(email="frank@example.com", sub="dx-sub-router-4"))
        state = await _start_and_get_state(client)
        callback = await client.get(
            "/api/v1/auth/oauth/dx/callback", params={"code": "auth-code", "state": state}
        )
        client.cookies.update(callback.cookies)

        response = await client.post("/api/v1/auth/logout")

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert fake.revoked == ["dx-access-token"]
        set_cookie_headers = response.headers.get_list("set-cookie")
        assert any(AuthCookies.ACCESS_TOKEN in h and "Max-Age=0" in h for h in set_cookie_headers)

        client.cookies.update(callback.cookies)  # simulate a stolen, not-yet-expired cookie
        me_after_logout = await client.get("/api/v1/auth/me")
        assert me_after_logout.status_code == 401
