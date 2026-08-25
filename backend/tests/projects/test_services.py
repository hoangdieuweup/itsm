"""Unit tests for app.modules.projects.services — Fake-based, no database."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.projects.access import resolve_project_membership
from app.modules.projects.config import projects_settings
from app.modules.projects.constants import EnvironmentType, ProjectLinkType
from app.modules.projects.exceptions import (
    EnvironmentNotFound,
    EnvironmentTypeAlreadyExists,
    InsufficientProjectAccess,
    ProjectLinkNotFound,
    ProjectMemberAlreadyExists,
    ProjectNotFound,
)
from app.modules.projects.repository import (
    AbstractEnvironmentRepository,
    AbstractProjectLinkRepository,
    AbstractProjectMemberRepository,
    AbstractProjectRepository,
    AbstractProjectRoleRepository,
    ProjectMemberRow,
    ProjectRoleRow,
)
from app.modules.projects.schemas import EnvironmentRead, ProjectLinkRead, ProjectRead
from app.modules.projects.services.add_project_member import AddProjectMember
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.delete_environment import DeleteEnvironment
from app.modules.projects.services.delete_project import DeleteProject
from app.modules.projects.services.delete_project_link import DeleteProjectLink
from app.modules.projects.services.list_project_members import ListProjectMembers
from app.modules.projects.services.list_visible_projects import ListVisibleProjects
from app.modules.projects.services.remove_project_member import RemoveProjectMember
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.schemas import PermissionRead, RoleSummary
from app.modules.users.public import UserRead


class FakeProjectRepository(AbstractProjectRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, ProjectRead] = {}

    async def get_by_id(self, entity_id: UUID) -> ProjectRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def create(self, *, name: str, description: str | None, created_by: UUID | None) -> ProjectRead:
        project = ProjectRead(
            id=uuid4(),
            name=name,
            description=description,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[project.id] = project
        return project

    async def update(self, project_id: UUID, *, name: str | None, description: str | None) -> ProjectRead:
        existing = self._rows[project_id]
        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "description": description if description is not None else existing.description,
            }
        )
        self._rows[project_id] = updated
        return updated

    async def delete(self, project_id: UUID) -> None:
        self._rows.pop(project_id, None)

    async def list_for_ids(self, project_ids: list[UUID]) -> list[ProjectRead]:
        return [self._rows[pid] for pid in project_ids if pid in self._rows]


class FakeEnvironmentRepository(AbstractEnvironmentRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, EnvironmentRead] = {}

    async def get_by_id(self, entity_id: UUID) -> EnvironmentRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[EnvironmentRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_project(self, project_id: UUID) -> list[EnvironmentRead]:
        return [e for e in self._rows.values() if e.project_id == project_id]

    async def find_by_project_and_type(
        self, project_id: UUID, env_type: EnvironmentType
    ) -> EnvironmentRead | None:
        return next(
            (e for e in self._rows.values() if e.project_id == project_id and e.type == env_type), None
        )

    async def create(
        self, *, project_id: UUID, type: EnvironmentType, name: str, base_url: str | None
    ) -> EnvironmentRead:
        env = EnvironmentRead(
            id=uuid4(),
            project_id=project_id,
            type=type,
            name=name,
            base_url=base_url,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[env.id] = env
        return env

    async def update(
        self, environment_id: UUID, *, name: str | None, base_url: str | None
    ) -> EnvironmentRead:
        existing = self._rows[environment_id]
        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "base_url": base_url if base_url is not None else existing.base_url,
            }
        )
        self._rows[environment_id] = updated
        return updated

    async def delete(self, environment_id: UUID) -> None:
        self._rows.pop(environment_id, None)


class FakeProjectLinkRepository(AbstractProjectLinkRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, ProjectLinkRead] = {}

    async def get_by_id(self, entity_id: UUID) -> ProjectLinkRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectLinkRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_project(self, project_id: UUID) -> list[ProjectLinkRead]:
        return [link for link in self._rows.values() if link.project_id == project_id]

    async def create(
        self, *, project_id: UUID, type: ProjectLinkType, name: str, url: str, is_default: bool
    ) -> ProjectLinkRead:
        link = ProjectLinkRead(
            id=uuid4(),
            project_id=project_id,
            type=type,
            name=name,
            url=url,
            is_default=is_default,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[link.id] = link
        return link

    async def update(self, link_id: UUID, *, name: str | None, url: str | None) -> ProjectLinkRead:
        existing = self._rows[link_id]
        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "url": url if url is not None else existing.url,
            }
        )
        self._rows[link_id] = updated
        return updated

    async def delete(self, link_id: UUID) -> None:
        self._rows.pop(link_id, None)


class FakeProjectMemberRepository(AbstractProjectMemberRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID], ProjectMemberRow] = {}

    async def get_by_id(self, entity_id: tuple) -> ProjectMemberRow | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectMemberRow], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def is_member(self, project_id: UUID, user_id: UUID) -> bool:
        return (project_id, user_id) in self._rows

    async def list_for_project(self, project_id: UUID) -> list[ProjectMemberRow]:
        return [row for row in self._rows.values() if row.project_id == project_id]

    async def list_project_ids_for_user(self, user_id: UUID) -> list[UUID]:
        return [row.project_id for row in self._rows.values() if row.user_id == user_id]

    async def add(self, project_id: UUID, user_id: UUID) -> None:
        self._rows[(project_id, user_id)] = ProjectMemberRow(
            project_id=project_id, user_id=user_id, created_at=datetime.now(UTC)
        )

    async def remove(self, project_id: UUID, user_id: UUID) -> None:
        self._rows.pop((project_id, user_id), None)

    async def set_project_role(self, project_id: UUID, user_id: UUID, project_role_id: UUID | None) -> None:
        existing = self._rows.get((project_id, user_id))
        if existing is not None:
            self._rows[(project_id, user_id)] = existing.model_copy(
                update={"project_role_id": project_role_id}
            )


class FakeProjectRoleRepository(AbstractProjectRoleRepository):
    def __init__(self, member_repo: "FakeProjectMemberRepository") -> None:
        self._rows: dict[UUID, ProjectRoleRow] = {}
        self._member_repo = member_repo

    async def get_by_id(self, entity_id: UUID) -> ProjectRoleRow | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRoleRow], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_project(self, project_id: UUID) -> list[ProjectRoleRow]:
        return [row for row in self._rows.values() if row.project_id == project_id]

    async def find_by_name(self, project_id: UUID, name: str) -> ProjectRoleRow | None:
        return next((r for r in self._rows.values() if r.project_id == project_id and r.name == name), None)

    async def create(self, *, project_id: UUID, name: str, permission_ids: list[UUID]) -> ProjectRoleRow:
        row = ProjectRoleRow(
            id=uuid4(),
            project_id=project_id,
            name=name,
            permission_ids=permission_ids,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[row.id] = row
        return row

    async def update(
        self, project_role_id: UUID, *, name: str | None, permission_ids: list[UUID] | None
    ) -> ProjectRoleRow:
        existing = self._rows[project_role_id]
        updated = existing.model_copy(
            update={
                "name": name if name is not None else existing.name,
                "permission_ids": permission_ids if permission_ids is not None else existing.permission_ids,
            }
        )
        self._rows[project_role_id] = updated
        return updated

    async def delete(self, project_role_id: UUID) -> None:
        self._rows.pop(project_role_id, None)

    async def permission_ids_for_member(self, project_id: UUID, user_id: UUID) -> list[UUID]:
        member = await self._member_repo.get_by_id((project_id, user_id))
        if member is None or member.project_role_id is None:
            return []
        role = self._rows.get(member.project_role_id)
        return role.permission_ids if role is not None else []


class FakeProjectsUnitOfWork(AbstractProjectsUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.projects = FakeProjectRepository()
        self.environments = FakeEnvironmentRepository()
        self.project_links = FakeProjectLinkRepository()
        self.project_members = FakeProjectMemberRepository()
        self.project_roles = FakeProjectRoleRepository(self.project_members)
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, UUID]] = []

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeAuditApi:
    """Duck-typed stand-in for app.modules.audit.public.AuditApi — records every
    call instead of writing to Mongo, so tests can assert an event was logged."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> None:
        self.events.append(kwargs)

    async def list_logs(self, **kwargs) -> tuple[list, int]:
        return [], 0


ACTOR_ID = uuid4()
ACTOR_EMAIL = "actor@example.com"


class TestCreateProject:
    async def test_creates_project_with_configured_default_links(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "https://jira.weup.vn")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "https://git.weup.vn")
        uow = FakeProjectsUnitOfWork()
        audit_api = FakeAuditApi()

        project = await CreateProject(uow, audit_api).execute(
            "Website A", "Marketing site", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert project.name == "Website A"
        links = await uow.project_links.list_for_project(project.id)
        assert {link.type for link in links} == {ProjectLinkType.JIRA, ProjectLinkType.GIT}
        assert all(link.is_default for link in links)
        assert uow.commits == 1
        assert audit_api.events[0]["action"] == "PROJECT_CREATED"
        assert await uow.project_members.is_member(project.id, ACTOR_ID)

    async def test_creates_project_with_no_default_links_when_unconfigured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "")
        uow = FakeProjectsUnitOfWork()

        project = await CreateProject(uow, FakeAuditApi()).execute(
            "Website B", None, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        links = await uow.project_links.list_for_project(project.id)
        assert links == []


class TestUpdateProject:
    async def test_updates_name(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Old", description=None, created_by=None)

        updated = await UpdateProject(uow, FakeAuditApi()).execute(
            project.id, name="New", description=None, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert updated.name == "New"
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await UpdateProject(uow, FakeAuditApi()).execute(
                uuid4(), name="X", description=None, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0


class TestDeleteProject:
    async def test_deletes_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Gone", description=None, created_by=None)

        await DeleteProject(uow, FakeAuditApi()).execute(
            project.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.projects.get_by_id(project.id) is None
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await DeleteProject(uow, FakeAuditApi()).execute(
                uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0


class TestCreateEnvironment:
    async def test_creates_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)

        env = await CreateEnvironment(uow, FakeAuditApi()).execute(
            project.id,
            EnvironmentType.DEV,
            "dev",
            "https://dev.website-a.example",
            actor_id=ACTOR_ID,
            actor_email=ACTOR_EMAIL,
        )

        assert env.type is EnvironmentType.DEV
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await CreateEnvironment(uow, FakeAuditApi()).execute(
                uuid4(), EnvironmentType.DEV, "dev", None, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

    async def test_rejects_duplicate_type_for_same_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        await uow.environments.create(
            project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None
        )

        with pytest.raises(EnvironmentTypeAlreadyExists):
            await CreateEnvironment(uow, FakeAuditApi()).execute(
                project.id, EnvironmentType.DEV, "dev-2", None, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestUpdateEnvironment:
    async def test_updates_name_and_base_url(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        env = await uow.environments.create(
            project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None
        )

        updated = await UpdateEnvironment(uow, FakeAuditApi()).execute(
            env.id,
            name="development",
            base_url="https://d.example",
            actor_id=ACTOR_ID,
            actor_email=ACTOR_EMAIL,
        )

        assert updated.name == "development"
        assert updated.base_url == "https://d.example"

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(EnvironmentNotFound):
            await UpdateEnvironment(uow, FakeAuditApi()).execute(
                uuid4(), name="x", base_url=None, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestDeleteEnvironment:
    async def test_deletes_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        env = await uow.environments.create(
            project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None
        )

        await DeleteEnvironment(uow, FakeAuditApi()).execute(
            env.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.environments.get_by_id(env.id) is None

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(EnvironmentNotFound):
            await DeleteEnvironment(uow, FakeAuditApi()).execute(
                uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestCreateProjectLink:
    async def test_creates_link_not_marked_default(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)

        link = await CreateProjectLink(uow).execute(
            project.id, ProjectLinkType.OTHER, "Runbook", "https://wiki.example/runbook"
        )

        assert link.is_default is False
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await CreateProjectLink(uow).execute(uuid4(), ProjectLinkType.OTHER, "X", "https://x.example")


class TestUpdateProjectLink:
    async def test_updates_name_and_url(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        link = await uow.project_links.create(
            project_id=project.id,
            type=ProjectLinkType.OTHER,
            name="Old",
            url="https://old.example",
            is_default=False,
        )

        updated = await UpdateProjectLink(uow).execute(link.id, name="New", url="https://new.example")

        assert updated.name == "New"
        assert updated.url == "https://new.example"

    async def test_rejects_unknown_link(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectLinkNotFound):
            await UpdateProjectLink(uow).execute(uuid4(), name="x", url=None)


class TestDeleteProjectLink:
    async def test_deletes_link(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        link = await uow.project_links.create(
            project_id=project.id,
            type=ProjectLinkType.OTHER,
            name="Old",
            url="https://old.example",
            is_default=False,
        )

        await DeleteProjectLink(uow).execute(link.id)

        assert await uow.project_links.get_by_id(link.id) is None

    async def test_rejects_unknown_link(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectLinkNotFound):
            await DeleteProjectLink(uow).execute(uuid4())


class FakeRbacApi:
    """Duck-typed stand-in for app.modules.rbac.public.RbacApi — only the
    methods this module's services actually call."""

    def __init__(
        self,
        *,
        manage_all: bool,
        global_permissions: list[str] | None = None,
        catalog_by_id: dict[UUID, str] | None = None,
    ) -> None:
        self._manage_all = manage_all
        self._global_permissions = global_permissions or []
        self._catalog_by_id = catalog_by_id or {}

    async def has_permission(self, user_id, resource, action) -> bool:
        return self._manage_all

    async def role_summary_for_user(self, user_id):
        return RoleSummary(roles=[], permissions=self._global_permissions, role_name=None)

    async def get_permissions_by_ids(self, ids: list[UUID]):
        return [
            PermissionRead(id=pid, resource=key.split(".")[0], action=key.split(".")[1], description_key="x")
            for pid, key in self._catalog_by_id.items()
            if pid in ids
        ]

    async def list_permission_catalog(self):
        return [
            PermissionRead(id=pid, resource=key.split(".")[0], action=key.split(".")[1], description_key="x")
            for pid, key in self._catalog_by_id.items()
        ]


class FakeUsersApi:
    """Duck-typed stand-in for app.modules.users.public.UsersApi."""

    def __init__(self, users: dict[UUID, object]) -> None:
        self._users = users

    async def get_user_by_id(self, user_id: UUID):
        return self._users.get(user_id)


class TestResolveProjectMembership:
    async def test_manage_all_bypasses_without_a_membership_row(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        user = UserRead.model_construct(id=uuid4(), email=ACTOR_EMAIL, name="Actor")

        await resolve_project_membership(project.id, user, FakeRbacApi(manage_all=True), uow)

    async def test_member_passes(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        await uow.project_members.add(project.id, ACTOR_ID)

        await resolve_project_membership(project.id, user, FakeRbacApi(manage_all=False), uow)

    async def test_non_member_without_manage_all_is_rejected(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        user = UserRead.model_construct(id=uuid4(), email=ACTOR_EMAIL, name="Actor")

        with pytest.raises(InsufficientProjectAccess):
            await resolve_project_membership(project.id, user, FakeRbacApi(manage_all=False), uow)


class TestListVisibleProjects:
    async def test_manage_all_sees_every_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        await uow.projects.create(name="A", description=None, created_by=None)
        await uow.projects.create(name="B", description=None, created_by=None)

        items, total = await ListVisibleProjects(uow, FakeRbacApi(manage_all=True)).execute(
            ACTOR_ID, limit=50, offset=0
        )

        assert total == 2
        assert {p.name for p in items} == {"A", "B"}

    async def test_non_manage_all_sees_only_member_projects(self) -> None:
        uow = FakeProjectsUnitOfWork()
        member_project = await uow.projects.create(name="Mine", description=None, created_by=None)
        await uow.projects.create(name="Not mine", description=None, created_by=None)
        await uow.project_members.add(member_project.id, ACTOR_ID)

        items, total = await ListVisibleProjects(uow, FakeRbacApi(manage_all=False)).execute(
            ACTOR_ID, limit=50, offset=0
        )

        assert total == 1
        assert items[0].name == "Mine"

    async def test_user_with_no_memberships_sees_nothing(self) -> None:
        uow = FakeProjectsUnitOfWork()
        await uow.projects.create(name="Not mine", description=None, created_by=None)

        items, total = await ListVisibleProjects(uow, FakeRbacApi(manage_all=False)).execute(
            ACTOR_ID, limit=50, offset=0
        )

        assert items == []
        assert total == 0


class TestListProjectMembers:
    async def test_lists_members_enriched_with_user_info(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        users_api = FakeUsersApi({ACTOR_ID: user})

        members = await ListProjectMembers(uow, users_api).execute(project.id)

        assert len(members) == 1
        assert members[0].email == ACTOR_EMAIL

    async def test_skips_a_member_row_whose_user_was_deleted(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        users_api = FakeUsersApi({})  # ACTOR_ID resolves to None

        members = await ListProjectMembers(uow, users_api).execute(project.id)

        assert members == []

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await ListProjectMembers(uow, FakeUsersApi({})).execute(uuid4())


class TestAddProjectMember:
    async def test_adds_member_and_audits(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        audit_api = FakeAuditApi()
        target_id = uuid4()

        await AddProjectMember(uow, audit_api).execute(
            project.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.project_members.is_member(project.id, target_id)
        assert audit_api.events[0]["action"] == "MEMBER_ADDED"

    async def test_rejects_duplicate_add(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        target_id = uuid4()
        await uow.project_members.add(project.id, target_id)

        with pytest.raises(ProjectMemberAlreadyExists):
            await AddProjectMember(uow, FakeAuditApi()).execute(
                project.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await AddProjectMember(uow, FakeAuditApi()).execute(
                uuid4(), uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestRemoveProjectMember:
    async def test_removes_member_and_audits(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        target_id = uuid4()
        await uow.project_members.add(project.id, target_id)
        audit_api = FakeAuditApi()

        await RemoveProjectMember(uow, audit_api).execute(
            project.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert not await uow.project_members.is_member(project.id, target_id)
        assert audit_api.events[0]["action"] == "MEMBER_REMOVED"

    async def test_removing_a_non_member_is_a_silent_no_op(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)

        await RemoveProjectMember(uow, FakeAuditApi()).execute(
            project.id, uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await RemoveProjectMember(uow, FakeAuditApi()).execute(
                uuid4(), uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )
