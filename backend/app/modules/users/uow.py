"""Transaction boundary for the users module."""

import logging
from abc import abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.users.repository import AbstractUserRepository, UserRepository

logger = logging.getLogger(__name__)


class AbstractUsersUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    users: AbstractUserRepository

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: int) -> None:
        """Queue a cache entity for invalidation once THIS uow's own commit() runs."""
        raise NotImplementedError

    @abstractmethod
    async def invalidate_now(self, entity: str, entity_id: int) -> None:
        """Bump a cache entity's version immediately, bypassing the mark_stale
        queue. For a cross-module orchestrator (e.g. auth's login flow) that
        writes through this module's facade but commits its OWN unit of
        work — this uow's commit() never runs in that case, so mark_stale
        would silently never flush. See UsersApi.invalidate_user and
        docs/superpowers/specs/2026-08-21-users-module-split-design.md.
        """
        raise NotImplementedError


class UsersUnitOfWork(AbstractUsersUnitOfWork):
    """Owns the transaction for the users module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, int]] = []
        self.users = UserRepository(session, cache)

    def mark_stale(self, entity: str, entity_id: int) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

    async def invalidate_now(self, entity: str, entity_id: int) -> None:
        """Bump a cache entity's version immediately, bypassing the queue."""
        await self._cache.bump_version(entity, entity_id)

    @database
    async def commit(self) -> None:
        """Commit the transaction, then invalidate every queued cache entity.

        Invalidation happens strictly after the database commit — bumping
        first would let a concurrent reader repopulate the cache from the
        pre-commit row. See references/caching.md#order-of-operations.
        """
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction and drop any queued invalidation."""
        await self._session.rollback()
        self._stale.clear()
        logger.warning("users unit of work rolled back")
