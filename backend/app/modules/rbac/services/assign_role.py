"""Use case: assign a role to an existing user (admin action)."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.constants import RbacCacheKeys, RbacTypes
from app.modules.rbac.exceptions import (
    CannotModifyProtectedAdmin,
    CannotRemoveLastAdmin,
    RoleNotFound,
    TargetUserNotFound,
)
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class AssignRole(AbstractUseCase):
    """user_lookup and is_protected are both injected rather than importing
    auth directly, so this service depends only on two narrow capabilities —
    dependencies wired in rbac/public.py's get_assign_role to
    app.modules.auth.public.AuthApi.get_user_by_id / .is_protected_admin."""

    def __init__(
        self,
        uow: AbstractRbacUnitOfWork,
        user_lookup: RbacTypes.UserLookup,
        is_protected: RbacTypes.ProtectionCheck,
    ) -> None:
        self._uow = uow
        self._user_lookup = user_lookup
        self._is_protected = is_protected

    @use_case
    async def execute(self, user_id: int, role_id: int) -> None:
        if await self._user_lookup(user_id) is None:
            raise TargetUserNotFound()
        if await self._is_protected(user_id):
            raise CannotModifyProtectedAdmin()
        role = await self._uow.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound()

        current = await self._uow.user_roles.get_role_for_user(user_id)
        if current is not None:
            admin_grants = await self._uow.roles.count_users_with_role(current.id)
            if RbacRules.blocks_last_admin_removal(current.name, admin_grants):
                raise CannotRemoveLastAdmin()

        await self._uow.user_roles.assign(user_id, role_id)
        self._uow.mark_stale(RbacCacheKeys.USER_ROLE_ENTITY, user_id)
        await self._uow.commit()
