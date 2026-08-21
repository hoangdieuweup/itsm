"""Use case: assign a set of roles to an existing user (admin action)."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.constants import RbacCacheKeys, RbacDefaults, RbacTypes
from app.modules.rbac.exceptions import (
    CannotModifyProtectedAdmin,
    CannotRemoveLastAdmin,
    RoleNotFound,
    TargetUserNotFound,
)
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class AssignRoles(AbstractUseCase):
    """Assign a set of roles to an existing user with admin protection."""

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
    async def execute(self, user_id: int, role_ids: list[int] | set[int]) -> None:
        if await self._user_lookup(user_id) is None:
            raise TargetUserNotFound()

        target_ids = set(role_ids)
        target_roles = []
        for rid in target_ids:
            role = await self._uow.roles.get_by_id(rid)
            if role is None:
                raise RoleNotFound()
            target_roles.append(role)

        new_role_names = {r.name for r in target_roles}

        # Protected break-glass admin check: cannot remove admin role from seeded admin
        if await self._is_protected(user_id) and RbacDefaults.ADMIN_ROLE_NAME not in new_role_names:
            raise CannotModifyProtectedAdmin()

        # Bus-factor rule check: if removing admin from current admin user, verify not last admin
        current_roles = await self._uow.user_roles.get_roles_for_user(user_id)
        current_role_names = {r.name for r in current_roles}

        if (
            RbacDefaults.ADMIN_ROLE_NAME in current_role_names
            and RbacDefaults.ADMIN_ROLE_NAME not in new_role_names
        ):
            admin_role = await self._uow.roles.find_by_name(RbacDefaults.ADMIN_ROLE_NAME)
            if admin_role is not None:
                admin_grants = await self._uow.roles.count_users_with_role(admin_role.id)
                if RbacRules.blocks_last_admin_removal(RbacDefaults.ADMIN_ROLE_NAME, admin_grants):
                    raise CannotRemoveLastAdmin()

        await self._uow.user_roles.assign_roles(user_id, target_ids)
        self._uow.mark_stale(RbacCacheKeys.USER_ROLE_ENTITY, user_id)
        await self._uow.commit()
