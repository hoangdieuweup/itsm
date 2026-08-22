"""Integration tests for app.modules.projects.router — real Postgres via testcontainers."""

from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


async def _login_with_permissions(
    client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]
) -> UUID:
    """Log in a real user and grant a role carrying exactly `permissions` —
    same trick tests/users/test_router.py uses."""
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


class TestCreateProject:
    async def test_requires_project_create_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.post("/api/v1/projects", json={"name": "Website A"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_creates_project_with_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[("project", "create")])

        response = await client.post(
            "/api/v1/projects", json={"name": "Website A", "description": "Marketing site"}
        )

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["name"] == "Website A"


class TestGetEnvironment:
    async def test_returns_one_environment(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project", "create"), ("environment", "create"), ("environment", "read")],
        )
        project_resp = await client.post("/api/v1/projects", json={"name": "Site"})
        project_id = project_resp.json()["data"]["id"]
        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments",
            json={"type": "dev", "name": "Dev"},
        )
        env_id = env_resp.json()["data"]["id"]

        response = await client.get(f"/api/v1/environments/{env_id}")

        assert response.status_code == 200
        assert response.json()["data"]["id"] == env_id
        assert response.json()["data"]["name"] == "Dev"

    async def test_returns_404_for_unknown_environment(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(client, engine, permissions=[("environment", "read")])

        response = await client.get(f"/api/v1/environments/{UUID(int=0)}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "projects_environment_not_found"

    async def test_requires_environment_read_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.get(f"/api/v1/environments/{UUID(int=0)}")

        assert response.status_code == 403


class TestProjectEnvironmentsAndLinks:
    async def test_full_lifecycle(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project", "create"),
                ("project", "read"),
                ("project", "update"),
                ("environment", "create"),
                ("environment", "read"),
                ("environment", "update"),
                ("environment", "delete"),
            ],
        )

        create_resp = await client.post("/api/v1/projects", json={"name": "Website A"})
        project_id = create_resp.json()["data"]["id"]

        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments",
            json={"type": "dev", "name": "dev", "baseUrl": "https://dev.example"},
        )
        assert env_resp.status_code == 200
        environment_id = env_resp.json()["data"]["id"]

        dup_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "dev-2"}
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["error"]["code"] == "projects_environment_type_already_exists"

        link_resp = await client.get(f"/api/v1/projects/{project_id}/links")
        assert link_resp.status_code == 200
        assert len(link_resp.json()["data"]) == 0  # PROJECTS__DEFAULT_JIRA_URL/GIT_URL unset in tests

        update_resp = await client.patch(
            f"/api/v1/environments/{environment_id}", json={"name": "development"}
        )
        assert update_resp.json()["data"]["name"] == "development"

        delete_resp = await client.delete(f"/api/v1/environments/{environment_id}")
        assert delete_resp.status_code == 200

        list_resp = await client.get(f"/api/v1/projects/{project_id}/environments")
        assert list_resp.json()["data"] == []
