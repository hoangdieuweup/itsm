"""List an account's managers, enriched with each user's email/name."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.schemas import CloudflareAccountManagerRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UsersApi


class ListCloudflareAccountManagers(AbstractUseCase):
    """Return every manager row for an account, enriched with the target
    user's email/name — the repository only knows user_id; resolving a
    human-readable identity is cross-module composition, which belongs in a
    use case, never the router or the repository."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, users_api: UsersApi) -> None:
        self._uow = uow
        self._users_api = users_api

    @use_case
    async def execute(self, account_id: UUID) -> list[CloudflareAccountManagerRead]:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()

        rows = await self._uow.account_managers.list_for_account(account_id)
        result: list[CloudflareAccountManagerRead] = []
        for row in rows:
            user = await self._users_api.get_user_by_id(row.user_id)
            if user is None:
                continue
            result.append(
                CloudflareAccountManagerRead(
                    user_id=row.user_id,
                    email=user.email,
                    name=user.name,
                    access_level=row.access_level,
                    created_at=row.created_at,
                )
            )
        return result
