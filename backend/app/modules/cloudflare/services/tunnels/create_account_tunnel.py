"""Create a new Cloudflare Tunnel on an account — account-level API proxy.

Called by POST /cloudflare-accounts/{account_id}/tunnels. Returns the raw
tunnel dict + connector install token from the Cloudflare API.
"""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class CreateAccountTunnel(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID, name: str) -> dict:
        credentials = await self._uow.accounts.get_credentials(account_id)
        if credentials is None:
            raise CloudflareAccountNotFound()
        cf_tunnel_id = await self._client.create_tunnel(
            cf_account_id=credentials.cf_account_id, api_token=credentials.api_token, name=name
        )
        token = await self._client.get_tunnel_token(
            cf_account_id=credentials.cf_account_id,
            cf_tunnel_id=cf_tunnel_id,
            api_token=credentials.api_token,
        )
        return {"cf_tunnel_id": cf_tunnel_id, "token": token}
