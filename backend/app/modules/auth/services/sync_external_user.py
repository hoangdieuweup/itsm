"""Use case: upsert the local User + Department from a DX profile."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.dx_core.client import DxUserProfile
from app.modules.auth.rules import AuthRules
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork


class SyncExternalUser(AbstractUseCase):
    """Sync a DX /oauth2/userinfo profile into the local users/departments tables.

    role is resolved and set only for a brand new user — see
    AbstractUserRepository.update_profile's docstring for why a later DX
    login must never overwrite a local admin's role/status decision.
    """

    def __init__(self, uow: AbstractAuthUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, profile: DxUserProfile) -> tuple[UserRead, bool]:
        """Return (user, is_new)."""
        department_id = None
        if profile.department is not None:
            department = await self._uow.departments.get_or_create_by_code(
                profile.department.code, profile.department.name
            )
            department_id = department.id

        existing = await self._uow.users.find_by_external_id(profile.sub)
        if existing is None:
            existing = await self._uow.users.find_by_email(profile.email)

        if existing is None:
            role = AuthRules.resolve_role(profile.roles[0] if profile.roles else None)
            user = await self._uow.users.create(
                email=profile.email,
                name=profile.name,
                role=role,
                external_user_id=profile.sub,
                employee_code=profile.employee_code,
                email_confirmed=profile.email_verified,
                department_id=department_id,
            )
            return user, True

        user = await self._uow.users.update_profile(
            existing.id,
            email=profile.email,
            name=profile.name,
            external_user_id=profile.sub,
            employee_code=profile.employee_code,
            email_confirmed=profile.email_verified,
            department_id=department_id,
        )
        return user, False
