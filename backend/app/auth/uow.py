"""Transaction boundary for the auth module."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repository import (
    AbstractDepartmentRepository,
    AbstractUserRepository,
    DepartmentRepository,
    UserRepository,
)
from app.markers import database
from app.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


class AbstractAuthUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    users: AbstractUserRepository
    departments: AbstractDepartmentRepository


class AuthUnitOfWork(AbstractAuthUnitOfWork):
    """Owns the transaction for the auth module's tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.users = UserRepository(session)
        self.departments = DepartmentRepository(session)

    @database
    async def commit(self) -> None:
        """Commit the transaction."""
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        logger.warning("auth unit of work rolled back")
