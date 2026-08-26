"""Unit tests for app.modules.projects.public.ProjectsApi — Fake-based, no database."""

from uuid import uuid4

import pytest

from app.modules.projects.exceptions import InsufficientProjectAccess
from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead
from tests.projects.test_services import ACTOR_EMAIL, ACTOR_ID, FakeProjectsUnitOfWork, FakeRbacApi


class TestResolveEffectivePermissions:
    async def test_returns_the_union_of_global_and_project_role_permissions(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        role_perm_id = uuid4()
        role = await uow.project_roles.create(
            project_id=project.id, name="dns-editor", permission_ids=[role_perm_id]
        )
        await uow.project_members.set_project_role(project.id, ACTOR_ID, role.id)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(
            manage_all=False,
            global_permissions=["project.read"],
            catalog_by_id={role_perm_id: "cloudflare_dns.create"},
        )
        api = ProjectsApi(uow)

        permissions = await api.resolve_effective_permissions(project.id, user, rbac_api)

        assert permissions == frozenset({"project.read", "cloudflare_dns.create"})

    async def test_raises_insufficient_project_access_for_a_non_member(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=[])
        api = ProjectsApi(uow)

        with pytest.raises(InsufficientProjectAccess):
            await api.resolve_effective_permissions(project.id, user, rbac_api)
