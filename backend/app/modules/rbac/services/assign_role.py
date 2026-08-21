"""Use case: assign a role to an existing user (admin action)."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.constants import RbacTypes
from app.modules.rbac.services.assign_roles import AssignRoles
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class AssignRole(AbstractUseCase):
    """Backwards-compatible single role assignment delegating to AssignRoles."""

    def __init__(
        self,
        uow: AbstractRbacUnitOfWork,
        user_lookup: RbacTypes.UserLookup,
        is_protected: RbacTypes.ProtectionCheck,
    ) -> None:
        self._delegate = AssignRoles(uow, user_lookup, is_protected)

    @use_case
    async def execute(self, user_id: int, role_id: int) -> None:
        await self._delegate.execute(user_id, [role_id])
