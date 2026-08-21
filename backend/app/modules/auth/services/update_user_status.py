"""Use case: block or unblock a user."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.auth.constants import AuthCacheKeys, UserStatus
from app.modules.auth.exceptions import CannotBlockLastAdmin, CannotModifyProtectedAdmin
from app.modules.auth.rules import AuthRules
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.rbac.public import RbacApi


class UpdateUserStatus(AbstractUseCase):
    """Block or unblock a user. Two independent rejections apply only when
    blocking: the seeded break-glass admin account is always protected
    (checked first, unconditional on admin count); the last admin is
    protected as long as no break-glass account exists to fall back on
    (rbac's own bus-factor rule, mirroring AssignRole for the analogous
    role-reassignment case)."""

    def __init__(self, uow: AbstractAuthUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, user_id: int, status: UserStatus) -> UserRead:
        if status == UserStatus.BLOCKED:
            target = await self._uow.users.get_by_id(user_id)
            if target is not None and AuthRules.is_protected_admin_email(target.email):
                raise CannotModifyProtectedAdmin()
            if await self._rbac_api.is_last_admin(user_id):
                raise CannotBlockLastAdmin()
        updated = await self._uow.users.set_status(user_id, status)
        self._uow.mark_stale(AuthCacheKeys.ENTITY, user_id)
        await self._uow.commit()
        return updated
