"""Shared Layer-2 membership-resolution logic. Lives in its own module — NOT
dependencies.py — so both dependencies.py's require_project_membership*
factory closures AND a service that needs to resolve membership directly
can import this without a cycle. Mirrors cloudflare/access.py's placement
rationale, simplified to a binary check (no access level to carry)."""

from uuid import UUID

from app.modules.projects.exceptions import InsufficientProjectAccess
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacActions, RbacApi, RbacResources
from app.modules.users.public import UserRead


async def resolve_project_membership(
    project_id: UUID, user: UserRead, rbac_api: RbacApi, uow: AbstractProjectsUnitOfWork
) -> None:
    """Raise InsufficientProjectAccess unless user holds project:manage_all
    or has a project_members row for project_id. No return value — binary
    membership has nothing else to carry, unlike Cloudflare's
    AccountAccessGrant (which also carries the resolved access_level)."""
    if await rbac_api.has_permission(user.id, RbacResources.PROJECT, RbacActions.MANAGE_ALL):
        return
    if not await uow.project_members.is_member(project_id, user.id):
        raise InsufficientProjectAccess()
