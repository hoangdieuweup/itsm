"""Integration tests for app.modules.users.router. Real Postgres via the
`client` fixture."""

from httpx import AsyncClient
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.config import users_settings
from app.modules.users.models import User


async def _login_with_permissions(
    client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]
) -> int:
    """Log in a real user (via a direct session cookie, same trick auth's
    own router tests use) and grant a role carrying exactly `permissions`."""
    async with engine.begin() as conn:
        user_result = await conn.execute(
            insert(User).values(
                email="actor@example.com",
                name="Actor",
                status="active",
                external_user_id="dx-actor",
                employee_code=None,
                email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]

        role_result = await conn.execute(insert(Role).values(name="test-role", is_system=False))
        role_id = role_result.inserted_primary_key[0]

        for resource, action in permissions:
            perm_result = await conn.execute(
                insert(Permission).values(resource=resource, action=action, description_key="x")
            )
            permission_id = perm_result.inserted_primary_key[0]
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))

        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": "test-jti"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


class TestListUsers:
    async def test_requires_user_read_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.get("/api/v1/users")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_lists_users_with_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[("user", "read")])

        response = await client.get("/api/v1/users")

        assert response.status_code == 200
        assert response.json()["data"]["total"] >= 1


class TestUpdateUserStatus:
    async def test_blocks_a_user(self, client: AsyncClient, engine: AsyncEngine) -> None:
        admin_id = await _login_with_permissions(client, engine, permissions=[("user", "update_status")])
        async with engine.begin() as conn:
            target = await conn.execute(
                insert(User).values(
                    email="target@example.com",
                    name="Target",
                    status="active",
                    external_user_id="dx-target",
                    employee_code=None,
                    email_confirmed=True,
                )
            )
            target_id = target.inserted_primary_key[0]

        response = await client.patch(f"/api/v1/users/{target_id}/status", json={"status": "blocked"})

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["status"] == "blocked"
        assert target_id != admin_id  # sanity: didn't accidentally block the actor itself

    async def test_rejects_blocking_the_last_admin(self, client: AsyncClient, engine: AsyncEngine) -> None:
        actor_id = await _login_with_permissions(client, engine, permissions=[("user", "update_status")])
        async with engine.begin() as conn:
            admin_role_id = (await conn.execute(select(Role.id).where(Role.name == "admin"))).scalar_one()
            update_status_permission_id = (
                await conn.execute(
                    select(Permission.id).where(
                        Permission.resource == "user", Permission.action == "update_status"
                    )
                )
            ).scalar_one()
            await conn.execute(
                insert(RolePermission).values(
                    role_id=admin_role_id, permission_id=update_status_permission_id
                )
            )
            await conn.execute(
                update(UserRole).where(UserRole.user_id == actor_id).values(role_id=admin_role_id)
            )

        response = await client.patch(f"/api/v1/users/{actor_id}/status", json={"status": "blocked"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "users_cannot_block_last_admin"

    async def test_rejects_blocking_the_protected_admin(
        self, client: AsyncClient, engine: AsyncEngine, monkeypatch
    ) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", "protected-router@example.com")
        await _login_with_permissions(client, engine, permissions=[("user", "update_status")])
        async with engine.begin() as conn:
            target = await conn.execute(
                insert(User).values(
                    email="protected-router@example.com",
                    name="Protected",
                    status="active",
                    external_user_id="dx-protected-router",
                    employee_code=None,
                    email_confirmed=True,
                )
            )
            target_id = target.inserted_primary_key[0]

        response = await client.patch(f"/api/v1/users/{target_id}/status", json={"status": "blocked"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "users_cannot_modify_protected_admin"
