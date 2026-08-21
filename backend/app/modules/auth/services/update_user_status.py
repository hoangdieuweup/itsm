"""Use case: block or unblock a user."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.auth.constants import UserStatus
from app.modules.auth.exceptions import CannotBlockLastOwner
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.rbac.public import RbacApi


class UpdateUserStatus(AbstractUseCase):
    """Block or unblock a user. Blocking the last owner is rejected — bus-factor
    safety, mirroring rbac's AssignRole for the analogous role-reassignment case."""

    def __init__(self, uow: AbstractAuthUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, user_id: int, status: UserStatus) -> UserRead:
        if status == UserStatus.BLOCKED and await self._rbac_api.is_last_owner(user_id):
            raise CannotBlockLastOwner()
        updated = await self._uow.users.set_status(user_id, status)
        await self._uow.commit()
        return updated
