"""Composition that can't live in dependencies.py.

get_update_user_status needs RbacApi (rbac.public), and rbac.public needs
users.public (for AssignRole's existence/protection checks), which needs
get_uow from users/dependencies.py — so putting this factory there would
close that cycle at load time. It lives here instead: nothing in
users.public or users.dependencies imports utils/, so this file can
safely reach into rbac.public without closing the cycle. See
docs/superpowers/specs/2026-08-21-users-module-split-design.md.

Deliberately not in router.py either — a router function only translates
HTTP into a use-case call (rule #10); composing the use case itself is a
different job, even when it has to live outside dependencies.py.
"""

from fastapi import Depends

from app.modules.rbac.public import RbacApi, get_rbac_api
from app.modules.users.dependencies import get_uow
from app.modules.users.services.update_user_status import UpdateUserStatus
from app.modules.users.uow import AbstractUsersUnitOfWork


async def get_update_user_status(
    uow: AbstractUsersUnitOfWork = Depends(get_uow),
    rbac_api: RbacApi = Depends(get_rbac_api),
) -> UpdateUserStatus:
    """Provide the block/unblock use case."""
    return UpdateUserStatus(uow, rbac_api)
