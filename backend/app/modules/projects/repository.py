"""Single access path to the projects, project_links, and environments tables."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.integrations.cache.client import CacheClient
from app.modules.projects.constants import EnvironmentType, ProjectLinkType, ProjectsCacheKeys
from app.modules.projects.models import Environment, Project, ProjectLink
from app.modules.projects.schemas import EnvironmentRead, ProjectLinkRead, ProjectRead


class AbstractProjectRepository(AbstractRepository[ProjectRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def create(self, *, name: str, description: str | None, created_by: UUID | None) -> ProjectRead:
        """Create a new project."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, project_id: UUID, *, name: str | None, description: str | None) -> ProjectRead:
        """Rename and/or redescribe a project. None means unchanged."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, project_id: UUID) -> None:
        """Delete a project. Cascades to its environments and links at the DB level."""
        raise NotImplementedError


class ProjectRepository(AbstractProjectRepository):
    """SQLAlchemy implementation. Every read/write of the projects table goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: UUID) -> ProjectRead | None:
        """Return one project, or None when it does not exist. Cache-aside."""
        return await self._cache.get_or_load(
            ProjectsCacheKeys.PROJECT_ENTITY, entity_id, ProjectRead, lambda: self._load_by_id(entity_id)
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> ProjectRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(Project).where(Project.id == entity_id))
        return ProjectRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRead], int]:
        """Return one page of projects together with the total count."""
        rows = await self._session.scalars(select(Project).order_by(Project.id).limit(limit).offset(offset))
        items = [ProjectRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Project))
        return items, total or 0

    @database
    async def create(self, *, name: str, description: str | None, created_by: UUID | None) -> ProjectRead:
        """Create a new project."""
        row = Project(name=name, description=description, created_by=created_by)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return ProjectRead.model_validate(row)

    @database
    async def update(self, project_id: UUID, *, name: str | None, description: str | None) -> ProjectRead:
        """Rename and/or redescribe a project. Caller must confirm project_id exists first."""
        row = await self._session.get(Project, project_id)
        if row is None:
            raise ValueError(f"project {project_id} does not exist")
        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        await self._session.flush()
        await self._session.refresh(row)
        return ProjectRead.model_validate(row)

    @database
    async def delete(self, project_id: UUID) -> None:
        """Delete a project. Caller must confirm project_id exists first."""
        row = await self._session.get(Project, project_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


class AbstractEnvironmentRepository(AbstractRepository[EnvironmentRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_project(self, project_id: UUID) -> list[EnvironmentRead]:
        """Return every environment belonging to a project."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_project_and_type(
        self, project_id: UUID, env_type: EnvironmentType
    ) -> EnvironmentRead | None:
        """Look up an environment by its (project_id, type) unique key."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, project_id: UUID, type: EnvironmentType, name: str, base_url: str | None
    ) -> EnvironmentRead:
        """Create a new environment."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, environment_id: UUID, *, name: str | None, base_url: str | None) -> EnvironmentRead:
        """Rename and/or re-point an environment. type is immutable."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, environment_id: UUID) -> None:
        """Delete an environment."""
        raise NotImplementedError


class EnvironmentRepository(AbstractEnvironmentRepository):
    """SQLAlchemy implementation. Every read/write of the environments table goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: UUID) -> EnvironmentRead | None:
        """Return one environment, or None when it does not exist. Cache-aside."""
        return await self._cache.get_or_load(
            ProjectsCacheKeys.ENVIRONMENT_ENTITY, entity_id, EnvironmentRead, lambda: self._load_by_id(entity_id)
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> EnvironmentRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(Environment).where(Environment.id == entity_id))
        return EnvironmentRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[EnvironmentRead], int]:
        """Required by AbstractRepository; environments are listed per-project in practice (list_for_project)."""
        rows = await self._session.scalars(
            select(Environment).order_by(Environment.id).limit(limit).offset(offset)
        )
        items = [EnvironmentRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Environment))
        return items, total or 0

    @database
    async def list_for_project(self, project_id: UUID) -> list[EnvironmentRead]:
        """Return every environment belonging to a project."""
        rows = await self._session.scalars(
            select(Environment).where(Environment.project_id == project_id).order_by(Environment.type)
        )
        return [EnvironmentRead.model_validate(row) for row in rows]

    @database
    async def find_by_project_and_type(
        self, project_id: UUID, env_type: EnvironmentType
    ) -> EnvironmentRead | None:
        """Look up an environment by its (project_id, type) unique key."""
        row = await self._session.scalar(
            select(Environment).where(Environment.project_id == project_id, Environment.type == env_type)
        )
        return EnvironmentRead.model_validate(row) if row else None

    @database
    async def create(
        self, *, project_id: UUID, type: EnvironmentType, name: str, base_url: str | None
    ) -> EnvironmentRead:
        """Create a new environment. Caller must confirm no (project_id, type) collision first."""
        row = Environment(project_id=project_id, type=type, name=name, base_url=base_url)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return EnvironmentRead.model_validate(row)

    @database
    async def update(self, environment_id: UUID, *, name: str | None, base_url: str | None) -> EnvironmentRead:
        """Rename and/or re-point an environment. Caller must confirm environment_id exists first."""
        row = await self._session.get(Environment, environment_id)
        if row is None:
            raise ValueError(f"environment {environment_id} does not exist")
        if name is not None:
            row.name = name
        if base_url is not None:
            row.base_url = base_url
        await self._session.flush()
        await self._session.refresh(row)
        return EnvironmentRead.model_validate(row)

    @database
    async def delete(self, environment_id: UUID) -> None:
        """Delete an environment. Caller must confirm environment_id exists first."""
        row = await self._session.get(Environment, environment_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


class AbstractProjectLinkRepository(AbstractRepository[ProjectLinkRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_project(self, project_id: UUID) -> list[ProjectLinkRead]:
        """Return every link belonging to a project."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, project_id: UUID, type: ProjectLinkType, name: str, url: str, is_default: bool
    ) -> ProjectLinkRead:
        """Create a new project link."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, link_id: UUID, *, name: str | None, url: str | None) -> ProjectLinkRead:
        """Rename and/or re-point a link. type/is_default are immutable after creation."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, link_id: UUID) -> None:
        """Delete a project link."""
        raise NotImplementedError


class ProjectLinkRepository(AbstractProjectLinkRepository):
    """SQLAlchemy implementation. Every read/write of the project_links table goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> ProjectLinkRead | None:
        """Return one link, or None when it does not exist. Not cached — links are read in small,
        already-cheap per-project batches (list_for_project), never hot single-row lookups."""
        row = await self._session.get(ProjectLink, entity_id)
        return ProjectLinkRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectLinkRead], int]:
        """Required by AbstractRepository; links are listed per-project in practice (list_for_project)."""
        rows = await self._session.scalars(
            select(ProjectLink).order_by(ProjectLink.id).limit(limit).offset(offset)
        )
        items = [ProjectLinkRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(ProjectLink))
        return items, total or 0

    @database
    async def list_for_project(self, project_id: UUID) -> list[ProjectLinkRead]:
        """Return every link belonging to a project."""
        rows = await self._session.scalars(
            select(ProjectLink).where(ProjectLink.project_id == project_id).order_by(ProjectLink.created_at)
        )
        return [ProjectLinkRead.model_validate(row) for row in rows]

    @database
    async def create(
        self, *, project_id: UUID, type: ProjectLinkType, name: str, url: str, is_default: bool
    ) -> ProjectLinkRead:
        """Create a new project link."""
        row = ProjectLink(project_id=project_id, type=type, name=name, url=url, is_default=is_default)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return ProjectLinkRead.model_validate(row)

    @database
    async def update(self, link_id: UUID, *, name: str | None, url: str | None) -> ProjectLinkRead:
        """Rename and/or re-point a link. Caller must confirm link_id exists first."""
        row = await self._session.get(ProjectLink, link_id)
        if row is None:
            raise ValueError(f"project link {link_id} does not exist")
        if name is not None:
            row.name = name
        if url is not None:
            row.url = url
        await self._session.flush()
        await self._session.refresh(row)
        return ProjectLinkRead.model_validate(row)

    @database
    async def delete(self, link_id: UUID) -> None:
        """Delete a project link. Caller must confirm link_id exists first."""
        row = await self._session.get(ProjectLink, link_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
