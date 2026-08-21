"""Unit tests for app.modules.projects.services — Fake-based, no database."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.projects.config import projects_settings
from app.modules.projects.constants import EnvironmentType, ProjectLinkType
from app.modules.projects.exceptions import (
    EnvironmentNotFound,
    EnvironmentTypeAlreadyExists,
    ProjectLinkNotFound,
    ProjectNotFound,
)
from app.modules.projects.repository import (
    AbstractEnvironmentRepository,
    AbstractProjectLinkRepository,
    AbstractProjectRepository,
)
from app.modules.projects.schemas import EnvironmentRead, ProjectLinkRead, ProjectRead
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.delete_environment import DeleteEnvironment
from app.modules.projects.services.delete_project import DeleteProject
from app.modules.projects.services.delete_project_link import DeleteProjectLink
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.uow import AbstractProjectsUnitOfWork


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


class FakeProjectsUnitOfWork(AbstractProjectsUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.projects = FakeProjectRepository()
        self.environments = FakeEnvironmentRepository()
        self.project_links = FakeProjectLinkRepository()
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, UUID]] = []

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class TestCreateProject:
    async def test_creates_project_with_configured_default_links(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "https://jira.weup.vn")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "https://git.weup.vn")
        uow = FakeProjectsUnitOfWork()

        project = await CreateProject(uow).execute("Website A", "Marketing site")

        assert project.name == "Website A"
        links = await uow.project_links.list_for_project(project.id)
        assert {link.type for link in links} == {ProjectLinkType.JIRA, ProjectLinkType.GIT}
        assert all(link.is_default for link in links)
        assert uow.commits == 1

    async def test_creates_project_with_no_default_links_when_unconfigured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "")
        uow = FakeProjectsUnitOfWork()

        project = await CreateProject(uow).execute("Website B", None)

        links = await uow.project_links.list_for_project(project.id)
        assert links == []


class TestUpdateProject:
    async def test_updates_name(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Old", description=None, created_by=None)

        updated = await UpdateProject(uow).execute(project.id, name="New", description=None)

        assert updated.name == "New"
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await UpdateProject(uow).execute(uuid4(), name="X", description=None)

        assert uow.commits == 0


class TestDeleteProject:
    async def test_deletes_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Gone", description=None, created_by=None)

        await DeleteProject(uow).execute(project.id)

        assert await uow.projects.get_by_id(project.id) is None
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await DeleteProject(uow).execute(uuid4())

        assert uow.commits == 0


class TestCreateEnvironment:
    async def test_creates_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)

        env = await CreateEnvironment(uow).execute(
            project.id, EnvironmentType.DEV, "dev", "https://dev.website-a.example"
        )

        assert env.type is EnvironmentType.DEV
        assert uow.commits == 1

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(ProjectNotFound):
            await CreateEnvironment(uow).execute(uuid4(), EnvironmentType.DEV, "dev", None)

    async def test_rejects_duplicate_type_for_same_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        await uow.environments.create(
            project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None
        )

        with pytest.raises(EnvironmentTypeAlreadyExists):
            await CreateEnvironment(uow).execute(project.id, EnvironmentType.DEV, "dev-2", None)


class TestUpdateEnvironment:
    async def test_updates_name_and_base_url(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        env = await uow.environments.create(
            project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None
        )

        updated = await UpdateEnvironment(uow).execute(
            env.id, name="development", base_url="https://d.example"
        )

        assert updated.name == "development"
        assert updated.base_url == "https://d.example"

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(EnvironmentNotFound):
            await UpdateEnvironment(uow).execute(uuid4(), name="x", base_url=None)


class TestDeleteEnvironment:
    async def test_deletes_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="Website A", description=None, created_by=None)
        env = await uow.environments.create(
            project_id=project.id, type=EnvironmentType.DEV, name="dev", base_url=None
        )

        await DeleteEnvironment(uow).execute(env.id)

        assert await uow.environments.get_by_id(env.id) is None

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeProjectsUnitOfWork()

        with pytest.raises(EnvironmentNotFound):
            await DeleteEnvironment(uow).execute(uuid4())


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
