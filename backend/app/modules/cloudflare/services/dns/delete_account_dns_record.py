"""Delete a DNS record on a zone in a Cloudflare account — account-level API proxy.

Called by DELETE /cloudflare-accounts/{account_id}/zones/{zone_id}/dns-records/{cf_record_id}.
"""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class DeleteAccountDnsRecord(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID, zone_id: str, cf_record_id: str) -> None:
        credentials = await self._uow.accounts.get_credentials(account_id)
        if credentials is None:
            raise CloudflareAccountNotFound()
        await self._client.delete_dns_record(
            zone_id=zone_id, cf_record_id=cf_record_id, api_token=credentials.api_token
        )
