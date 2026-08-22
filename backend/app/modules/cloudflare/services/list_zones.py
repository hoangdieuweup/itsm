"""List zones available to bind, for the zone-picker endpoint."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.schemas import ZoneOption
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListZones(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID) -> list[ZoneOption]:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(account_id)
        if ciphertext is None:
            raise CloudflareAccountNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        return await self._client.list_zones(cf_account_id=account.cf_account_id, api_token=plaintext)
