"""Use case: delete a custom role."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.exceptions import RoleInUse, RoleNotFound, SystemRoleImmutable
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class DeleteRole(AbstractUseCase):
    """Blocked for a system role (RbacRules.can_delete_role) and for a role still
    granted to at least one user — reassign them first."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, role_id: int) -> None:
        role = await self._uow.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound()
        if not RbacRules.can_delete_role(role):
            raise SystemRoleImmutable()
        if await self._uow.roles.count_users_with_role(role_id) > 0:
            raise RoleInUse()
        await self._uow.roles.delete(role_id)
        await self._uow.commit()
