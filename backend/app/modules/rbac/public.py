"""Contract exposed to other modules. This is the ONLY file another module
may import from rbac — enforced by scripts/check_module_boundaries.py.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.auth.public import AuthApi, UserRead, get_auth_api
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.dependencies import get_uow
from app.modules.rbac.exceptions import PermissionDenied
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import RoleSummary
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.services.assign_role import AssignRole
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


async def get_assign_role(
    uow: AbstractRbacUnitOfWork = Depends(get_uow),
    auth_api: AuthApi = Depends(get_auth_api),
) -> AssignRole:
    """Provide the assign-role use case, wired to auth's user-existence check."""
    return AssignRole(uow, auth_api.get_user_by_id)


def require_permission(resource: str, action: str):
    """Return a dependency that 403s unless the current user's role grants
    resource.action. Routes ask 'can this user do X,' never 'does this user
    have role Y' — see references/rbac.md."""

    async def check(
        auth_api: AuthApi = Depends(get_auth_api),
        uow: AbstractRbacUnitOfWork = Depends(get_uow),
    ) -> UserRead:
        user = auth_api.current_user()
        if not await uow.user_roles.user_has_permission(user.id, resource, action):
            raise PermissionDenied(resource=resource, action=action)
        return user

    return check
