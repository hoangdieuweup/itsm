"""Data facade exposed to other modules — RbacApi has no dependency on auth,
which is what lets auth's own composition root (auth/dependencies.py,
auth/services/authenticate.py) import from here without a circular import.

For gating a router's endpoints behind a permission check, see guards.py
instead — that file needs auth.public (to resolve the current user), which
is exactly the dependency this file stays free of.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.dependencies import get_uow
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import RoleSummary
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class RbacApi:
    """Facade over role/permission lookups other modules need."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @facade
    async def assign_default_role(self, user_id: int) -> None:
        """Grant the seeded default role. See services/assign_default_role.py."""
        await AssignDefaultRole(self._uow).execute(user_id)

    @facade
    async def role_summary_for_user(self, user_id: int) -> RoleSummary:
        """Return role name + flat 'resource.action' permission strings, for
        auth/me to compose into the session the frontend's PermissionProvider seeds from."""
        role = await self._uow.user_roles.get_role_for_user(user_id)
        if role is None:
            return RoleSummary(role_name="", permissions=[])
        return RoleSummary(
            role_name=role.name, permissions=[f"{p.resource}.{p.action}" for p in role.permissions]
        )

    @facade
    async def is_last_owner(self, user_id: int) -> bool:
        """True if user_id holds the owner role and is the only one who does —
        used by auth's UpdateUserStatus to block blocking the last owner."""
        role = await self._uow.user_roles.get_role_for_user(user_id)
        if role is None or role.name != RbacDefaults.OWNER_ROLE_NAME:
            return False
        owner_grants = await self._uow.roles.count_users_with_role(role.id)
        return RbacRules.blocks_last_owner_removal(role.name, owner_grants)


async def get_rbac_api(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> RbacApi:
    """Provide the facade to other modules."""
    return RbacApi(uow)
