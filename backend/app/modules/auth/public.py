"""Contract exposed to other modules.

Other modules import this file and nothing else from auth. Reaching into
repository.py or models.py couples them to storage details and makes this
module impossible to extract later.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.auth.dependencies import get_current_user, get_uow
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork


class AuthApi:
    """Facade over the signed in user, plus a narrow by-id lookup for other
    modules' cross-module existence checks (e.g. rbac validating a role
    assignment's target user)."""

    def __init__(self, user: UserRead, uow: AbstractAuthUnitOfWork) -> None:
        self._user = user
        self._uow = uow

    @facade
    def current_user(self) -> UserRead:
        """Return the signed in user resolved for this request."""
        return self._user

    @facade
    async def get_user_by_id(self, user_id: int) -> UserRead | None:
        """Look up any user by id. For a single existence check from another
        module — never for bulk reads, which would mean that module wants its
        own list_page-shaped facade method instead."""
        return await self._uow.users.get_by_id(user_id)


async def get_auth_api(
    user: UserRead = Depends(get_current_user),
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
) -> AuthApi:
    """Provide the facade to other modules."""
    return AuthApi(user, uow)
