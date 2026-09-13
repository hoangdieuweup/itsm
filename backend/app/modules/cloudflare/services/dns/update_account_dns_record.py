"""Update a DNS record on a zone in a Cloudflare account — account-level API proxy.

Called by PATCH /cloudflare-accounts/{account_id}/zones/{zone_id}/dns-records/{cf_record_id}.
"""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class UpdateAccountDnsRecord(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(
        self,
        account_id: UUID,
        zone_id: str,
        cf_record_id: str,
        *,
        record_type: str,
        name: str,
        content: str,
        ttl: int = 1,
        proxied: bool = False,
        priority: int | None = None,
    ) -> None:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(account_id)
        if ciphertext is None:
            raise CloudflareAccountNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        await self._client.update_dns_record(
            zone_id=zone_id,
            cf_record_id=cf_record_id,
            api_token=plaintext,
            record_type=record_type,
            name=name,
            content=content,
            ttl=ttl,
            proxied=proxied,
            priority=priority,
        )
