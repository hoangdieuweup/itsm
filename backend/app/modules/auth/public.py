"""Contract exposed to other modules.

Other modules import this file and nothing else from auth. Reaching into
dependencies.py directly couples them to plumbing and makes this module
impossible to extract later.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.auth.dependencies import get_current_user
from app.modules.users.public import UserRead


class AuthApi:
    """Facade over the signed in user for other modules that need to know
    who is making the current request (e.g. rbac's require_permission)."""

    def __init__(self, user: UserRead) -> None:
        self._user = user

    @facade
    def current_user(self) -> UserRead:
        """Return the signed in user resolved for this request."""
        return self._user


async def get_auth_api(user: UserRead = Depends(get_current_user)) -> AuthApi:
    """Provide the facade to other modules."""
    return AuthApi(user)
