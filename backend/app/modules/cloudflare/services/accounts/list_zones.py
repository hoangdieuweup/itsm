"""List zones available to bind, for the zone-picker endpoint."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.schemas import ZoneOption
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListZones(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID) -> list[ZoneOption]:
        credentials = await self._uow.accounts.get_credentials(account_id)
        if credentials is None:
            raise CloudflareAccountNotFound()
        return await self._client.list_zones(
            cf_account_id=credentials.cf_account_id, api_token=credentials.api_token
        )
