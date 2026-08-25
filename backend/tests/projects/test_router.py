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


async def _switch_to(client: AsyncClient, user_id: UUID, *, email: str) -> None:
    """Re-authenticate `client` as an already-created user, without re-inserting
    them — for tests that alternate between two previously logged-in identities."""
    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": f"test-jti-{email}"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)


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
        # require_project_permission_for_environment resolves the environment
        # (to find its project_id) BEFORE checking the caller's permission —
        # same "resolve parent first" order Cloudflare's own
        # require_account_access_for_environment already uses. A permission-
        # less caller must therefore be tested against a REAL environment,
        # not a nonexistent one (which 404s regardless of permissions).
        await _login_with_permissions(
            client,
            engine,
            permissions=[("project", "create"), ("environment", "create"), ("environment", "read")],
            email="owner-env-perm@example.com",
        )
        project_resp = await client.post("/api/v1/projects", json={"name": "Site"})
        project_id = project_resp.json()["data"]["id"]
        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "Dev"}
        )
        env_id = env_resp.json()["data"]["id"]

        await _login_with_permissions(client, engine, permissions=[], email="no-perms@example.com")

        response = await client.get(f"/api/v1/environments/{env_id}")

        assert response.status_code == 403

    async def test_returns_404_for_unknown_environment_even_without_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.get(f"/api/v1/environments/{UUID(int=0)}")

        assert response.status_code == 404


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
                ("project_link", "read"),
                ("project_link", "manage"),
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
            permissions=[
                ("project", "read"),
                ("project", "update"),
                ("project", "manage_all"),
                ("project_member", "read"),
                ("project_member", "manage"),
            ],
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


class TestProjectRoleUnionGrant:
    async def test_project_role_grants_environment_update_scoped_to_one_project(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """The whole point of the feature: a collaborator with ZERO global
        environment permissions gets elevated to editor on ONE project via
        a project role, and the grant never leaks to a sibling project."""
        admin_id = await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project", "create"),
                ("environment", "create"),
                ("environment", "update"),
                ("project_member", "manage"),
                ("project_role", "manage"),
                ("project_role", "read"),
                ("project", "read"),
                ("permission", "read"),
            ],
            email="admin@example.com",
        )
        project_a = (await client.post("/api/v1/projects", json={"name": "A"})).json()["data"]
        project_b = (await client.post("/api/v1/projects", json={"name": "B"})).json()["data"]
        env_a = (
            await client.post(
                f"/api/v1/projects/{project_a['id']}/environments", json={"type": "dev", "name": "dev"}
            )
        ).json()["data"]
        env_b = (
            await client.post(
                f"/api/v1/projects/{project_b['id']}/environments", json={"type": "dev", "name": "dev"}
            )
        ).json()["data"]

        perms_resp = await client.get("/api/v1/rbac/permissions")
        env_update_id = next(
            p["id"]
            for p in perms_resp.json()["data"]
            if p["resource"] == "environment" and p["action"] == "update"
        )
        role_resp = await client.post(
            f"/api/v1/projects/{project_a['id']}/roles",
            json={"name": "env-editor", "permissionIds": [env_update_id]},
        )
        assert role_resp.status_code == 200
        role_id = role_resp.json()["data"]["id"]

        collaborator_id = await _login_with_permissions(
            client, engine, permissions=[("project", "read")], email="collaborator@example.com"
        )
        await _switch_to(client, admin_id, email="admin@example.com")
        member_body = {"userId": str(collaborator_id)}
        await client.post(f"/api/v1/projects/{project_a['id']}/members", json=member_body)
        await client.post(f"/api/v1/projects/{project_b['id']}/members", json=member_body)
        assign_resp = await client.put(
            f"/api/v1/projects/{project_a['id']}/members/{collaborator_id}/role",
            json={"projectRoleId": role_id},
        )
        assert assign_resp.status_code == 200

        await _switch_to(client, collaborator_id, email="collaborator@example.com")

        update_a = await client.patch(f"/api/v1/environments/{env_a['id']}", json={"name": "renamed"})
        assert update_a.status_code == 200

        update_b = await client.patch(f"/api/v1/environments/{env_b['id']}", json={"name": "renamed"})
        assert update_b.status_code == 403
        assert update_b.json()["error"]["code"] == "projects_project_permission_denied"

        perms_a = await client.get(f"/api/v1/projects/{project_a['id']}/permissions")
        assert "environment.update" in perms_a.json()["data"]["permissions"]
        perms_b = await client.get(f"/api/v1/projects/{project_b['id']}/permissions")
        assert "environment.update" not in perms_b.json()["data"]["permissions"]


class TestProjectRoleAllowlist:
    async def test_rejects_a_non_assignable_permission_at_the_api_boundary(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project", "create"),
                ("project_role", "manage"),
                ("permission", "read"),
                ("user", "update_status"),
            ],
            email="admin2@example.com",
        )
        project = (await client.post("/api/v1/projects", json={"name": "A"})).json()["data"]
        perms_resp = await client.get("/api/v1/rbac/permissions")
        sneaky_id = next(
            p["id"]
            for p in perms_resp.json()["data"]
            if p["resource"] == "user" and p["action"] == "update_status"
        )

        resp = await client.post(
            f"/api/v1/projects/{project['id']}/roles", json={"name": "sneaky", "permissionIds": [sneaky_id]}
        )

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "projects_permission_not_project_assignable"


class TestProjectRoleBackwardCompatibility:
    async def test_null_project_role_member_still_works_via_global_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("project", "create"),
                ("environment", "create"),
                ("environment", "update"),
                ("project", "read"),
            ],
            email="solo@example.com",
        )
        project = (await client.post("/api/v1/projects", json={"name": "A"})).json()["data"]
        env = (
            await client.post(
                f"/api/v1/projects/{project['id']}/environments", json={"type": "dev", "name": "dev"}
            )
        ).json()["data"]

        resp = await client.patch(f"/api/v1/environments/{env['id']}", json={"name": "renamed"})

        assert resp.status_code == 200
