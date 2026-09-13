"""Shared Layer-2 membership-resolution logic. Lives in its own module — NOT
dependencies.py — so both dependencies.py's require_project_membership*
factory closures AND a service that needs to resolve membership directly
can import this without a cycle. Mirrors cloudflare/access.py's placement
rationale, simplified to a binary check (no access level to carry)."""

from uuid import UUID

from app.modules.projects.exceptions import InsufficientProjectAccess
from app.modules.projects.rules import ProjectRoleRules
from app.modules.projects.schemas import ProjectPermissionGrant
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacActions, RbacApi, RbacResources
from app.modules.users.public import UserRead


async def resolve_project_membership(
    project_id: UUID, user: UserRead, rbac_api: RbacApi, uow: AbstractProjectsUnitOfWork
) -> bool:
    """Raise InsufficientProjectAccess unless user holds project:manage_all
    or has a project_members row for project_id. Returns True when it was
    manage_all that admitted them — resolve_project_permissions reuses that
    bit instead of asking rbac_api a second time."""
    if await rbac_api.has_permission(user.id, RbacResources.PROJECT, RbacActions.MANAGE_ALL):
        return True
    if not await uow.project_members.is_member(project_id, user.id):
        raise InsufficientProjectAccess()
    return False


async def resolve_project_permissions(
    project_id: UUID, user: UserRead, rbac_api: RbacApi, uow: AbstractProjectsUnitOfWork
) -> ProjectPermissionGrant:
    """Membership first, then the effective permission set: global
    permissions UNIONed with the caller's ProjectRole inside this project,
    plus the scoped surface when they hold project:manage_all."""
    manages_all = await resolve_project_membership(project_id, user, rbac_api, uow)

    summary = await rbac_api.role_summary_for_user(user.id)
    global_keys = frozenset(summary.permissions)

    role_permission_ids = await uow.project_roles.permission_ids_for_member(project_id, user.id)
    project_permissions = await rbac_api.get_permissions_by_ids(role_permission_ids)
    project_keys = frozenset(f"{p.resource}.{p.action}" for p in project_permissions)

    effective = ProjectRoleRules.effective_permissions(
        global_keys, project_keys, manages_all_projects=manages_all
    )
    return ProjectPermissionGrant(user=user, project_id=project_id, permissions=effective)
