"""List DNS records for a specific zone on a Cloudflare account — account-level.

Called by GET /cloudflare-accounts/{account_id}/zones/{zone_id}/dns-records.
Returns raw DNS record data directly from the Cloudflare API.
"""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListAccountDnsRecords(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID, zone_id: str) -> list[dict]:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(account_id)
        if ciphertext is None:
            raise CloudflareAccountNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        return await self._client.list_dns_records(zone_id=zone_id, api_token=plaintext)
