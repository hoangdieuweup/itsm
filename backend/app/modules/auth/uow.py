"""Transaction boundary for the auth module."""

import logging
from abc import abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.auth.repository import AbstractUserRepository, UserRepository

logger = logging.getLogger(__name__)


class AbstractAuthUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    users: AbstractUserRepository

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: int) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        raise NotImplementedError


class AuthUnitOfWork(AbstractAuthUnitOfWork):
    """Owns the transaction for the auth module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, int]] = []
        self.users = UserRepository(session, cache)

    def mark_stale(self, entity: str, entity_id: int) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

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
        logger.warning("auth unit of work rolled back")
