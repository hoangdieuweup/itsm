"""Single access path to the environments table."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.integrations.cache.client import CacheClient
from app.modules.projects.constants import EnvironmentType, ProjectsCacheKeys
from app.modules.projects.exceptions import (
    EnvironmentNotFound,
)
from app.modules.projects.models import (
    Environment,
)
from app.modules.projects.schemas import EnvironmentRead


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
    async def update(
        self, environment_id: UUID, *, name: str | None, base_url: str | None
    ) -> EnvironmentRead:
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
            ProjectsCacheKeys.ENVIRONMENT_ENTITY,
            entity_id,
            EnvironmentRead,
            lambda: self._load_by_id(entity_id),
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> EnvironmentRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(Environment).where(Environment.id == entity_id))
        return EnvironmentRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[EnvironmentRead], int]:
        """Required by AbstractRepository; environments are listed per-project
        in practice (list_for_project)."""
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
    async def update(
        self, environment_id: UUID, *, name: str | None, base_url: str | None
    ) -> EnvironmentRead:
        """Rename and/or re-point an environment. Caller must confirm environment_id exists first."""
        row = await self._session.get(Environment, environment_id)
        if row is None:
            raise EnvironmentNotFound()
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
