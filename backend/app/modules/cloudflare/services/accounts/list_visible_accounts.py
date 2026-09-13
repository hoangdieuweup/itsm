"""List Cloudflare accounts visible to the current user."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.schemas import CloudflareAccountRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.rbac.public import RbacActions, RbacApi, RbacResources


class ListVisibleCloudflareAccounts(AbstractUseCase):
    """Return every account the current user can see: all of them if they
    hold cloudflare_account:manage_all, otherwise only the accounts where
    they have a cloudflare_account_managers row (any level). A user with
    neither gets an empty list, not a 403 — Layer 1's `view` permission
    already gated reaching this use case at all; this narrows WHICH accounts,
    exactly like every other Layer-2 check in this module."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, user_id: UUID) -> list[CloudflareAccountRead]:
        if await self._rbac_api.has_permission(
            user_id, RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE_ALL
        ):
            return await self._uow.accounts.list_all()

        manager_rows = await self._uow.account_managers.list_for_user(user_id)
        account_ids = [row.cloudflare_account_id for row in manager_rows]
        return await self._uow.accounts.list_for_ids(account_ids)
