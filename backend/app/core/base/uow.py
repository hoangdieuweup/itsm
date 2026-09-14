"""Abstract unit-of-work contract every module's concrete UoW implements."""

from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from app.core.base.markers import database


class AbstractUnitOfWork(ABC):
    """Async context manager owning one transaction boundary.

    __aexit__ rolls back automatically on any exception, so a concrete
    subclass only ever has to implement commit() and rollback().
    """

    async def __aenter__(self) -> "AbstractUnitOfWork":
        """Enter the transactional scope."""
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Roll back whenever the block raised."""
        if exc_type is not None:
            await self.rollback()

    @database
    @abstractmethod
    async def commit(self) -> None:
        """Commit the transaction, applying any deferred side effect only on success."""
        raise NotImplementedError

    @database
    @abstractmethod
    async def rollback(self) -> None:
        """Roll back the transaction, undoing any deferred side effect too."""
        raise NotImplementedError


class CacheVersionBumper(Protocol):
    """What a cached unit of work needs from the cache: bump one entity's version.

    Declared here rather than imported because app.core holds mechanism and may
    never import app.integrations.cache — the root-is-mechanism contract in
    .importlinter enforces that.
    """

    async def bump_version(self, entity: str, entity_id: UUID | int | str) -> None:
        """Invalidate every cached read of one entity."""
        ...


class AbstractCachedUnitOfWork(AbstractUnitOfWork):
    """A unit of work whose repositories serve cache-aside reads."""

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: UUID | int | str) -> None:
        """Queue a cache entity for invalidation once THIS uow's own commit() runs."""
        raise NotImplementedError
