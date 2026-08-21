"""Dependency wiring for the rbac module.

The composition root: the only place that names a concrete class
(RbacUnitOfWork) instead of its Abstract* contract.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork, RbacUnitOfWork


async def get_uow(session: AsyncSession = Depends(get_session)) -> RbacUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return RbacUnitOfWork(session)


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
