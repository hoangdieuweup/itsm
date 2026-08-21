"""Use case: create a new custom role with an initial permission set."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.exceptions import DuplicateRoleName, UnknownPermissionId
from app.modules.rbac.schemas import RoleRead
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class CreateRole(AbstractUseCase):
    """Create a role. Always is_system=False — only the seed script creates system roles."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, name: str, permission_ids: list[int]) -> RoleRead:
        if await self._uow.roles.find_by_name(name) is not None:
            raise DuplicateRoleName()
        found = await self._uow.permissions.find_by_ids(permission_ids)
        if len(found) != len(set(permission_ids)):
            raise UnknownPermissionId()
        role = await self._uow.roles.create(name=name, is_system=False, permission_ids=permission_ids)
        await self._uow.commit()
        return role
