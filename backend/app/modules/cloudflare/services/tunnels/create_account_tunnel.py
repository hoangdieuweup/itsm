"""Create a new Cloudflare Tunnel on an account — account-level API proxy.

Called by POST /cloudflare-accounts/{account_id}/tunnels. Returns the raw
tunnel dict + connector install token from the Cloudflare API.
"""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class CreateAccountTunnel(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID, name: str) -> dict:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(account_id)
        if ciphertext is None:
            raise CloudflareAccountNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        cf_tunnel_id = await self._client.create_tunnel(
            cf_account_id=account.cf_account_id, api_token=plaintext, name=name
        )
        token = await self._client.get_tunnel_token(
            cf_account_id=account.cf_account_id, cf_tunnel_id=cf_tunnel_id, api_token=plaintext
        )
        return {"cf_tunnel_id": cf_tunnel_id, "token": token}
