"""Dependency wiring for the rbac module.

The composition root: the only place that names a concrete class
(RbacUnitOfWork) instead of its Abstract* contract.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.services.assign_roles import AssignRoles
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork, RbacUnitOfWork
from app.modules.users.public import UsersApi, get_users_api


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> RbacUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return RbacUnitOfWork(session, cache)


async def get_create_role(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> CreateRole:
    """Provide the create-role use case."""
    return CreateRole(uow)


async def get_update_role(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> UpdateRole:
    """Provide the update-role use case."""
    return UpdateRole(uow)


async def get_delete_role(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> DeleteRole:
    """Provide the delete-role use case."""
    return DeleteRole(uow)


async def get_assign_default_role(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> AssignDefaultRole:
    """Provide the default-role-grant use case, used by auth's SSO sync flow."""
    return AssignDefaultRole(uow)


async def get_assign_role(
    uow: AbstractRbacUnitOfWork = Depends(get_uow),
    users_api: UsersApi = Depends(get_users_api),
) -> AssignRole:
    """Provide the assign-role use case, wired to users' existence and
    protected-admin checks."""
    return AssignRole(uow, users_api.get_user_by_id, users_api.is_protected_admin)


async def get_assign_roles(
    uow: AbstractRbacUnitOfWork = Depends(get_uow),
    users_api: UsersApi = Depends(get_users_api),
) -> AssignRoles:
    """Provide the assign-roles use case, wired to users' existence and
    protected-admin checks."""
    return AssignRoles(uow, users_api.get_user_by_id, users_api.is_protected_admin)
