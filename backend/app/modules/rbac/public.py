"""Contract exposed to other modules. This is the ONLY file another module
may import from rbac — enforced by scripts/check_module_boundaries.py.
"""

from uuid import UUID

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.rbac.constants import RbacActions, RbacDefaults, RbacResources
from app.modules.rbac.dependencies import get_uow, require_any_permission, require_permission
from app.modules.rbac.models import Permission, Role, UserRole
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import PermissionRead, RoleSummary
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork

__all__ = [
    "Permission",
    "PermissionRead",
    "Role",
    "UserRole",
    "RbacDefaults",
    "RbacResources",
    "RbacActions",
    "RbacApi",
    "get_rbac_api",
    "require_permission",
    "require_any_permission",
]


class RbacApi:
    """Facade over role/permission lookups other modules need."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @facade
    async def assign_default_role(self, user_id: UUID) -> None:
        """Grant the seeded default role. See services/assign_default_role.py."""
        await AssignDefaultRole(self._uow).execute(user_id)

    @facade
    async def role_summary_for_user(self, user_id: UUID) -> RoleSummary:
        """Return role names + union of 'resource.action' permission strings, for
        auth/me to compose into the session the frontend's PermissionProvider seeds from."""
        roles = await self._uow.user_roles.get_roles_for_user(user_id)
        if not roles:
            return RoleSummary(roles=[], permissions=[], role_name="")
        role_names = [r.name for r in roles]
        perms = {f"{p.resource}.{p.action}" for r in roles for p in r.permissions}
        return RoleSummary(
            roles=role_names,
            permissions=sorted(perms),
            role_name=role_names[0],
        )

    @facade
    async def get_role_names_for_users(self, user_ids: list[UUID]) -> dict[UUID, list[str]]:
        """Return a mapping of user_id -> list[role_name] for a batch of users."""
        return await self._uow.user_roles.get_roles_for_users(user_ids)

    @facade
    async def is_last_admin(self, user_id: UUID) -> bool:
        """True if user_id holds the admin role and is the only one who does —
        used by users' UpdateUserStatus to block blocking the last admin."""
        roles = await self._uow.user_roles.get_roles_for_user(user_id)
        admin_role = next((r for r in roles if r.name == RbacDefaults.ADMIN_ROLE_NAME), None)
        if admin_role is None:
            return False
        admin_grants = await self._uow.roles.count_users_with_role(admin_role.id)
        return RbacRules.blocks_last_admin_removal(admin_role.name, admin_grants)

    @facade
    async def has_permission(self, user_id: UUID, resource: str, action: str) -> bool:
        """Direct boolean permission check for a module that needs to compose
        it with a SECOND, module-owned authorization check (e.g. cloudflare's
        manage_all bypass inside require_account_access) — require_permission
        is a 403-raising route dependency, not reusable as a plain boolean."""
        return await self._uow.user_roles.user_has_permission(user_id, resource, action)

    @facade
    async def get_permissions_by_ids(self, ids: list[UUID]) -> list[PermissionRead]:
        """Resolve permission ids to their resource.action + description —
        used by a project role's editor UI and by union-permission
        resolution (see projects/access.py)."""
        return await self._uow.permissions.find_by_ids(ids)

    @facade
    async def list_permission_catalog(self) -> list[PermissionRead]:
        """Return the full, fixed permission catalog — backs the project-
        role editor's assignable-permissions picker."""
        return await self._uow.permissions.list_all()


async def get_rbac_api(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> RbacApi:
    """Provide the facade to other modules."""
    return RbacApi(uow)
