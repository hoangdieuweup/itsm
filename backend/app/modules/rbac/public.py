"""Contract exposed to other modules. This is the ONLY file another module
may import from rbac — enforced by scripts/check_module_boundaries.py.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.dependencies import get_uow
from app.modules.rbac.exceptions import PermissionDenied
from app.modules.rbac.models import Permission, Role, UserRole
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import RoleSummary
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork
from app.modules.users.public import UserRead, UsersApi, get_users_api

__all__ = [
    "Permission",
    "Role",
    "UserRole",
    "RbacApi",
    "get_rbac_api",
    "get_assign_role",
    "require_permission",
]


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
    async def get_role_names_for_users(self, user_ids: list[int]) -> dict[int, str]:
        """Return a mapping of user_id -> role_name for a batch of users."""
        return await self._uow.user_roles.get_roles_for_users(user_ids)

    @facade
    async def is_last_admin(self, user_id: int) -> bool:
        """True if user_id holds the admin role and is the only one who does —
        used by users' UpdateUserStatus to block blocking the last admin."""
        role = await self._uow.user_roles.get_role_for_user(user_id)
        if role is None or role.name != RbacDefaults.ADMIN_ROLE_NAME:
            return False
        admin_grants = await self._uow.roles.count_users_with_role(role.id)
        return RbacRules.blocks_last_admin_removal(role.name, admin_grants)


async def get_rbac_api(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> RbacApi:
    """Provide the facade to other modules."""
    return RbacApi(uow)


async def get_assign_role(
    uow: AbstractRbacUnitOfWork = Depends(get_uow),
    users_api: UsersApi = Depends(get_users_api),
) -> AssignRole:
    """Provide the assign-role use case, wired to users' existence and
    protected-admin checks."""
    return AssignRole(uow, users_api.get_user_by_id, users_api.is_protected_admin)


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
