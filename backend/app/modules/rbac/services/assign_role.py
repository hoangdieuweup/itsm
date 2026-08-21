"""Use case: assign a role to an existing user (admin action)."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.constants import RbacTypes
from app.modules.rbac.exceptions import CannotRemoveLastAdmin, RoleNotFound, TargetUserNotFound
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class AssignRole(AbstractUseCase):
    """user_lookup is injected rather than importing auth directly, so this
    service depends only on a narrow capability — dependencies.py wires it to
    app.modules.auth.public.AuthApi.get_user_by_id (the one facade call to the
    module that actually owns the users table)."""

    def __init__(self, uow: AbstractRbacUnitOfWork, user_lookup: RbacTypes.UserLookup) -> None:
        self._uow = uow
        self._user_lookup = user_lookup

    @use_case
    async def execute(self, user_id: int, role_id: int) -> None:
        if await self._user_lookup(user_id) is None:
            raise TargetUserNotFound()
        role = await self._uow.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound()

        current = await self._uow.user_roles.get_role_for_user(user_id)
        if current is not None:
            admin_grants = await self._uow.roles.count_users_with_role(current.id)
            if RbacRules.blocks_last_admin_removal(current.name, admin_grants):
                raise CannotRemoveLastAdmin()

        await self._uow.user_roles.assign(user_id, role_id)
        await self._uow.commit()
