"""List DNS records for a specific zone on a Cloudflare account — account-level.

Called by GET /cloudflare-accounts/{account_id}/zones/{zone_id}/dns-records.
Returns raw DNS record data directly from the Cloudflare API.
"""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListAccountDnsRecords(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID, zone_id: str) -> list[dict]:
        credentials = await self._uow.accounts.get_credentials(account_id)
        if credentials is None:
            raise CloudflareAccountNotFound()
        return await self._client.list_dns_records(zone_id=zone_id, api_token=credentials.api_token)
