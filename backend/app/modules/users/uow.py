"""Transaction boundary for the users module."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.uow import AbstractCachedUnitOfWork
from app.core.uow import CachedSqlAlchemyUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.users.repository import AbstractUserRepository, UserRepository


class AbstractUsersUnitOfWork(AbstractCachedUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    users: AbstractUserRepository

    @abstractmethod
    async def invalidate_now(self, entity: str, entity_id: UUID | int | str) -> None:
        """Bump a cache entity's version immediately, bypassing the mark_stale
        queue. For a cross-module orchestrator (e.g. auth's login flow) that
        writes through this module's facade but commits its OWN unit of
        work — this uow's commit() never runs in that case, so mark_stale
        would silently never flush. See UsersApi.invalidate_user and
        docs/superpowers/specs/2026-08-21-users-module-split-design.md.
        """
        raise NotImplementedError


class UsersUnitOfWork(AbstractUsersUnitOfWork, CachedSqlAlchemyUnitOfWork):
    """Owns the transaction for the users module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        super().__init__(session, cache)
        self.users = UserRepository(session, cache)

    async def invalidate_now(self, entity: str, entity_id: UUID | int | str) -> None:
        """Bump a cache entity's version immediately, bypassing the queue."""
        await self._cache.bump_version(entity, entity_id)
