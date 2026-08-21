"""Integration tests for app.modules.rbac.router. Real Postgres via the `client`
fixture. Seeds roles/permissions directly through the ORM (bypassing the seed
script's own idempotency logic, which isn't the thing under test here) and
issues a real session cookie the same way auth's own router tests do."""

from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.auth.models import User
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole


async def _seed_permission(engine: AsyncEngine, resource: str, action: str) -> int:
    async with engine.begin() as conn:
        result = await conn.execute(
            insert(Permission).values(resource=resource, action=action, description="x")
        )
        return result.inserted_primary_key[0]


async def _seed_role(engine: AsyncEngine, name: str, *, is_system: bool, permission_ids: list[int]) -> int:
    async with engine.begin() as conn:
        result = await conn.execute(insert(Role).values(name=name, is_system=is_system))
        role_id = result.inserted_primary_key[0]
        for permission_id in permission_ids:
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))
        return role_id


async def _seed_user(engine: AsyncEngine, *, email: str, external_user_id: str) -> int:
    async with engine.begin() as conn:
        result = await conn.execute(
            insert(User).values(
                email=email,
                name="Test User",
                status="active",
                external_user_id=external_user_id,
                employee_code=None,
                email_confirmed=True,
            )
        )
        return result.inserted_primary_key[0]


async def _login_as(client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]) -> int:
    """Seed a user with a role granting exactly `permissions`, and a valid session
    cookie for them, without going through the real DX OAuth flow."""
    permission_ids = [await _seed_permission(engine, r, a) for r, a in permissions]
    role_id = await _seed_role(engine, "test-role", is_system=False, permission_ids=permission_ids)
    user_id = await _seed_user(engine, email="perm-test@example.com", external_user_id="dx-perm-test")
    async with engine.begin() as conn:
        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": "test-jti"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


class TestRolesRequirePermission:
    async def test_list_roles_without_permission_is_403(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_as(client, engine, permissions=[])

        response = await client.get("/api/v1/rbac/roles")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_list_roles_with_permission_succeeds(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_as(client, engine, permissions=[("role", "read")])

        response = await client.get("/api/v1/rbac/roles")

        body = response.json()
        assert response.status_code == 200
        assert body["success"] is True
        assert any(r["name"] == "test-role" for r in body["data"]["items"])


class TestCreateRole:
    async def test_creates_a_role(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_as(client, engine, permissions=[("role", "create")])

        response = await client.post("/api/v1/rbac/roles", json={"name": "support", "permissionIds": []})

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["name"] == "support"
        assert body["data"]["isSystem"] is False


class TestAssignUserRole:
    async def test_assigns_role_to_target_user(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_as(client, engine, permissions=[("user", "assign_role")])
        target_role_id = await _seed_role(engine, "viewer", is_system=False, permission_ids=[])
        target_user_id = await _seed_user(engine, email="target@example.com", external_user_id="dx-target")

        response = await client.patch(
            f"/api/v1/rbac/users/{target_user_id}/role", json={"roleId": target_role_id}
        )

        assert response.status_code == 200
        async with engine.begin() as conn:
            result = await conn.execute(select(UserRole.role_id).where(UserRole.user_id == target_user_id))
            assert result.scalar_one() == target_role_id

    async def test_unknown_target_user_is_404(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_as(client, engine, permissions=[("user", "assign_role")])
        role_id = await _seed_role(engine, "viewer2", is_system=False, permission_ids=[])

        response = await client.patch("/api/v1/rbac/users/999999/role", json={"roleId": role_id})

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "rbac_target_user_not_found"
