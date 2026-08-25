"""Integration tests for app.modules.projects.router — real Postgres via testcontainers."""

from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


async def _login_with_permissions(
    client: AsyncClient,
    engine: AsyncEngine,
    *,
    permissions: list[tuple[str, str]],
    email: str = "actor@example.com",
) -> UUID:
    """Create a user with a fresh role granting exactly `permissions`, then
    authenticate `client` as them. Idempotent on the Permission row itself —
    the project-membership tests routinely log in more than one user per test
    with an overlapping permission set (e.g. two users both needing
    `project:read`), which would otherwise violate the (resource, action)
    unique constraint on a second insert of the same tuple within one test."""
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


class TestProjectMembership:
    async def test_non_member_with_role_permissions_is_rejected(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """The literal regression case: a role grants project:read/update, but
        the caller was never added as a member — every project-scoped route
        must 403, not just quietly succeed because the role permits it."""
        await _login_with_permissions(
            client, engine, permissions=[("project", "create")], email="owner@example.com"
        )
        create_resp = await client.post("/api/v1/projects", json={"name": "Website A"})
        project_id = create_resp.json()["data"]["id"]

        await _login_with_permissions(
            client,
            engine,
            permissions=[("project", "read"), ("project", "update"), ("project", "delete")],
            email="outsider@example.com",
        )

        get_resp = await client.get(f"/api/v1/projects/{project_id}")
        assert get_resp.status_code == 403
        assert get_resp.json()["error"]["code"] == "projects_insufficient_project_access"

        patch_resp = await client.patch(f"/api/v1/projects/{project_id}", json={"name": "Renamed"})
        assert patch_resp.status_code == 403

        delete_resp = await client.delete(f"/api/v1/projects/{project_id}")
        assert delete_resp.status_code == 403

        list_resp = await client.get("/api/v1/projects")
        assert project_id not in [p["id"] for p in list_resp.json()["data"]["items"]]

    async def test_manage_all_bypasses_membership(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(
            client, engine, permissions=[("project", "create")], email="owner2@example.com"
        )
        create_resp = await client.post("/api/v1/projects", json={"name": "Website A"})
        project_id = create_resp.json()["data"]["id"]

        await _login_with_permissions(
            client,
            engine,
            permissions=[("project", "read"), ("project", "manage_all")],
            email="admin@example.com",
        )

        get_resp = await client.get(f"/api/v1/projects/{project_id}")
        assert get_resp.status_code == 200

        list_resp = await client.get("/api/v1/projects")
        assert project_id in [p["id"] for p in list_resp.json()["data"]["items"]]

    async def test_creator_is_auto_added_as_member(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(
            client, engine, permissions=[("project", "create"), ("project", "read")]
        )

        create_resp = await client.post("/api/v1/projects", json={"name": "Website A"})
        project_id = create_resp.json()["data"]["id"]

        get_resp = await client.get(f"/api/v1/projects/{project_id}")
        assert get_resp.status_code == 200

    async def test_add_then_remove_member_via_endpoints(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project", "create"), ("project", "update")],
            email="owner3@example.com",
        )
        create_resp = await client.post("/api/v1/projects", json={"name": "Website A"})
        project_id = create_resp.json()["data"]["id"]

        target_id = await _login_with_permissions(
            client,
            engine,
            permissions=[("project", "read"), ("project", "update")],
            email="target@example.com",
        )
        forbidden_resp = await client.get(f"/api/v1/projects/{project_id}")
        assert forbidden_resp.status_code == 403

        await _login_with_permissions(
            client,
            engine,
            permissions=[("project", "read"), ("project", "update"), ("project", "manage_all")],
            email="admin2@example.com",
        )
        add_resp = await client.post(
            f"/api/v1/projects/{project_id}/members", json={"userId": str(target_id)}
        )
        assert add_resp.status_code == 200

        dup_resp = await client.post(
            f"/api/v1/projects/{project_id}/members", json={"userId": str(target_id)}
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["error"]["code"] == "projects_project_member_already_exists"

        members_resp = await client.get(f"/api/v1/projects/{project_id}/members")
        assert target_id in [UUID(m["userId"]) for m in members_resp.json()["data"]]

        remove_resp = await client.delete(f"/api/v1/projects/{project_id}/members/{target_id}")
        assert remove_resp.status_code == 200

        members_after_resp = await client.get(f"/api/v1/projects/{project_id}/members")
        assert target_id not in [UUID(m["userId"]) for m in members_after_resp.json()["data"]]
