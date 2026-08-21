"""Transaction boundary for the rbac module."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.modules.rbac.repository import (
    AbstractPermissionRepository,
    AbstractRoleRepository,
    AbstractUserRoleRepository,
    PermissionRepository,
    RoleRepository,
    UserRoleRepository,
)

logger = logging.getLogger(__name__)


class AbstractRbacUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    roles: AbstractRoleRepository
    permissions: AbstractPermissionRepository
    user_roles: AbstractUserRoleRepository


class RbacUnitOfWork(AbstractRbacUnitOfWork):
    """Owns the transaction for the rbac module's tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.roles = RoleRepository(session)
        self.permissions = PermissionRepository(session)
        self.user_roles = UserRoleRepository(session)

    @database
    async def commit(self) -> None:
        """Commit the transaction."""
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        logger.warning("rbac unit of work rolled back")
