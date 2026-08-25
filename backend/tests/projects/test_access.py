"""Unit tests for app.modules.projects.access — Fake-based, no database."""

from uuid import uuid4

import pytest

from app.modules.projects.access import resolve_project_permissions
from app.modules.projects.exceptions import InsufficientProjectAccess
from app.modules.users.public import UserRead
from tests.projects.test_services import ACTOR_EMAIL, ACTOR_ID, FakeProjectsUnitOfWork, FakeRbacApi


class TestResolveProjectPermissions:
    async def test_null_project_role_yields_exactly_the_global_permission_set(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=["project.read"])

        grant = await resolve_project_permissions(project.id, user, rbac_api, uow)

        assert grant.permissions == frozenset({"project.read"})

    async def test_project_role_adds_environment_update_beyond_global_read_only(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        role_perm_id = uuid4()
        role = await uow.project_roles.create(
            project_id=project.id, name="env-editor", permission_ids=[role_perm_id]
        )
        await uow.project_members.set_project_role(project.id, ACTOR_ID, role.id)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(
            manage_all=False,
            global_permissions=["project.read"],
            catalog_by_id={role_perm_id: "environment.update"},
        )

        grant = await resolve_project_permissions(project.id, user, rbac_api, uow)

        assert grant.permissions == frozenset({"project.read", "environment.update"})

    async def test_non_member_without_manage_all_is_rejected(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        user = UserRead.model_construct(id=uuid4(), email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=[])

        with pytest.raises(InsufficientProjectAccess):
            await resolve_project_permissions(project.id, user, rbac_api, uow)

    async def test_manage_all_bypasses_membership_but_grant_is_still_just_their_global_set(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        user = UserRead.model_construct(id=uuid4(), email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=True, global_permissions=["project.manage_all"])

        grant = await resolve_project_permissions(project.id, user, rbac_api, uow)

        assert grant.permissions == frozenset({"project.manage_all"})
