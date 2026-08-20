"""Contract exposed to other modules.

Other modules import this file and nothing else from auth. Reaching into
repository.py or models.py couples them to storage details and makes this
module impossible to extract later.
"""

from fastapi import Depends

from app.auth.dependencies import get_current_user
from app.auth.schemas import UserRead
from app.markers import facade


class AuthApi:
    """Read only facade over the signed in user."""

    def __init__(self, user: UserRead) -> None:
        self._user = user

    @facade
    def current_user(self) -> UserRead:
        """Return the signed in user resolved for this request."""
        return self._user


async def get_auth_api(user: UserRead = Depends(get_current_user)) -> AuthApi:
    """Provide the facade to other modules."""
    return AuthApi(user)
