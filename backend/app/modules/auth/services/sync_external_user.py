"""Use case: upsert the local User from a DX profile."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.dx_core.client import DxUserProfile
from app.modules.users.public import UserRead, UsersApi


class SyncExternalUser(AbstractUseCase):
    """Sync a DX /oauth2/userinfo profile into the users table via UsersApi
    — auth no longer owns this table.

    Role assignment is no longer this use case's job — see
    AuthenticateWithDx, which grants the default rbac role only for a brand
    new user, right after this returns is_new=True. Does not commit or
    invalidate the cache itself: AuthenticateWithDx owns both, since it
    orchestrates this alongside DX-token-save and role-assignment writes
    that must all succeed or fail together in one transaction.
    """

    def __init__(self, users_api: UsersApi) -> None:
        self._users_api = users_api

    @use_case
    async def execute(self, profile: DxUserProfile) -> tuple[UserRead, bool]:
        """Return (user, is_new)."""
        existing = await self._users_api.find_by_external_id(profile.sub)
        if existing is None:
            existing = await self._users_api.find_by_email(profile.email)

        if existing is None:
            user = await self._users_api.create(
                email=profile.email,
                name=profile.name,
                external_user_id=profile.sub,
                employee_code=profile.employee_code,
                email_confirmed=profile.email_verified,
            )
            return user, True

        user = await self._users_api.update_profile(
            existing.id,
            email=profile.email,
            name=profile.name,
            external_user_id=profile.sub,
            employee_code=profile.employee_code,
            email_confirmed=profile.email_verified,
        )
        return user, False
