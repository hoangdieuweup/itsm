"""Use case: upsert the local User from a DX profile."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.dx_core.client import DxUserProfile
from app.modules.auth.constants import AuthCacheKeys
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork


class SyncExternalUser(AbstractUseCase):
    """Sync a DX /oauth2/userinfo profile into the local users table.

    Role assignment is no longer this use case's job — see
    AuthenticateWithDx, which grants the default rbac role only for a brand
    new user, right after this returns is_new=True.
    """

    def __init__(self, uow: AbstractAuthUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, profile: DxUserProfile) -> tuple[UserRead, bool]:
        """Return (user, is_new)."""
        existing = await self._uow.users.find_by_external_id(profile.sub)
        if existing is None:
            existing = await self._uow.users.find_by_email(profile.email)

        if existing is None:
            user = await self._uow.users.create(
                email=profile.email,
                name=profile.name,
                external_user_id=profile.sub,
                employee_code=profile.employee_code,
                email_confirmed=profile.email_verified,
            )
            self._uow.mark_stale(AuthCacheKeys.ENTITY, user.id)
            return user, True

        user = await self._uow.users.update_profile(
            existing.id,
            email=profile.email,
            name=profile.name,
            external_user_id=profile.sub,
            employee_code=profile.employee_code,
            email_confirmed=profile.email_verified,
        )
        self._uow.mark_stale(AuthCacheKeys.ENTITY, user.id)
        return user, False
