"""require_permission — the dependency every module's router (including
rbac's own) gates its endpoints with, plus the one use-case factory that
needs the same auth.public dependency (get_assign_role).

Split from public.py specifically because this file needs auth.public (to
resolve the current user), and public.py's RbacApi must not — auth's own
composition root imports RbacApi from public.py, and if public.py pulled in
auth.public too, that would close an import cycle back through
auth.dependencies. See public.py's docstring for the other half of this split.
"""

from fastapi import Depends

from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.auth.schemas import UserRead
from app.modules.rbac.dependencies import get_uow
from app.modules.rbac.exceptions import PermissionDenied
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork


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
