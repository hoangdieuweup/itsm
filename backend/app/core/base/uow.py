"""Abstract unit-of-work contract every module's concrete UoW implements."""

from abc import ABC, abstractmethod

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
