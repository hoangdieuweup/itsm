"""Transaction boundary for the rbac module."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.uow import AbstractCachedUnitOfWork
from app.core.uow import CachedSqlAlchemyUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.rbac.repository import (
    AbstractPermissionRepository,
    AbstractRoleRepository,
    AbstractUserRoleRepository,
    PermissionRepository,
    RoleRepository,
    UserRoleRepository,
)


class AbstractRbacUnitOfWork(AbstractCachedUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    roles: AbstractRoleRepository
    permissions: AbstractPermissionRepository
    user_roles: AbstractUserRoleRepository


class RbacUnitOfWork(AbstractRbacUnitOfWork, CachedSqlAlchemyUnitOfWork):
    """Owns the transaction for the rbac module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        super().__init__(session, cache)
        self.roles = RoleRepository(session, cache)
        self.permissions = PermissionRepository(session)
        self.user_roles = UserRoleRepository(session, cache)
