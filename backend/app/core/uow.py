"""SQLAlchemy-backed unit of work mechanism every module's concrete unit of work extends.

A module's uow.py is then only its repository list: the transaction boundary and
the cache-invalidation queue live here, once.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractCachedUnitOfWork, AbstractUnitOfWork, CacheVersionBumper

logger = logging.getLogger(__name__)


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """Commits and rolls back one request-scoped AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def commit(self) -> None:
        """Commit the transaction."""
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        logger.warning("%s rolled back", type(self).__name__)


class CachedSqlAlchemyUnitOfWork(SqlAlchemyUnitOfWork, AbstractCachedUnitOfWork):
    """Adds the stale-entity queue for modules whose repositories cache reads.

    Cache versions are bumped strictly after the database commit — bumping first
    would let a concurrent reader repopulate the cache from the pre-commit row,
    per references/caching.md#order-of-operations — and the queue is dropped on
    rollback.
    """

    def __init__(self, session: AsyncSession, cache: CacheVersionBumper) -> None:
        super().__init__(session)
        self._cache = cache
        self._stale: list[tuple[str, UUID | int | str]] = []

    def mark_stale(self, entity: str, entity_id: UUID | int | str) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

    @database
    async def commit(self) -> None:
        """Commit the transaction, then invalidate every queued cache entity."""
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        """Drop any queued invalidation, then roll back the transaction."""
        self._stale.clear()
        await super().rollback()
