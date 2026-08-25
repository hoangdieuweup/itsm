"""Transaction boundary for the projects module."""

import logging
from abc import abstractmethod
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.projects.repository import (
    AbstractEnvironmentRepository,
    AbstractProjectLinkRepository,
    AbstractProjectMemberRepository,
    AbstractProjectRepository,
    EnvironmentRepository,
    ProjectLinkRepository,
    ProjectMemberRepository,
    ProjectRepository,
)

logger = logging.getLogger(__name__)


class AbstractProjectsUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    projects: AbstractProjectRepository
    environments: AbstractEnvironmentRepository
    project_links: AbstractProjectLinkRepository
    project_members: AbstractProjectMemberRepository

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        """Queue a cache entity for invalidation once THIS uow's own commit() runs."""
        raise NotImplementedError


class ProjectsUnitOfWork(AbstractProjectsUnitOfWork):
    """Owns the transaction for the projects module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, UUID]] = []
        self.projects = ProjectRepository(session, cache)
        self.environments = EnvironmentRepository(session, cache)
        self.project_links = ProjectLinkRepository(session)
        self.project_members = ProjectMemberRepository(session)

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

    @database
    async def commit(self) -> None:
        """Commit the transaction, then invalidate every queued cache entity — strictly
        after the database commit, per references/caching.md#order-of-operations."""
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction and drop any queued invalidation."""
        await self._session.rollback()
        self._stale.clear()
        logger.warning("projects unit of work rolled back")
