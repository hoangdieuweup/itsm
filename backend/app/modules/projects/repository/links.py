"""Single access path to the project_links table."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.projects.constants import ProjectLinkType
from app.modules.projects.exceptions import (
    ProjectLinkNotFound,
)
from app.modules.projects.models import (
    ProjectLink,
)
from app.modules.projects.schemas import ProjectLinkRead


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
            raise ProjectLinkNotFound()
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
