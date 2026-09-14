"""Single access path to the projects table."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.core.pagination import PageQuery
from app.integrations.cache.client import CacheClient
from app.modules.projects.constants import ProjectsCacheKeys
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectRead


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

    @abstractmethod
    async def list_for_ids(self, project_ids: list[UUID]) -> list[ProjectRead]:
        """Return every project whose id is in project_ids, in no particular
        order — backs the membership-filtered GET /projects list."""
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
        rows, total = await PageQuery.fetch_rows(
            self._session,
            Project,
            limit=limit,
            offset=offset,
            order_by=Project.id,
        )
        return [ProjectRead.model_validate(row) for row in rows], total

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
            raise ProjectNotFound()
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

    @database
    async def list_for_ids(self, project_ids: list[UUID]) -> list[ProjectRead]:
        """Return every project whose id is in project_ids."""
        if not project_ids:
            return []
        rows = await self._session.scalars(select(Project).where(Project.id.in_(project_ids)))
        return [ProjectRead.model_validate(row) for row in rows]
