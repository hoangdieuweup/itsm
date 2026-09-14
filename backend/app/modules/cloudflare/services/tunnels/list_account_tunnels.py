"""List all tunnels on a Cloudflare account — account-level, not environment-scoped.

Called by GET /cloudflare-accounts/{account_id}/tunnels. Returns raw tunnel
data directly from the Cloudflare API (id, name, status, type, connections,
timestamps) — no local DB model for these, it's a live API proxy.
"""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListAccountTunnels(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID) -> list[dict]:
        credentials = await self._uow.accounts.get_credentials(account_id)
        if credentials is None:
            raise CloudflareAccountNotFound()
        return await self._client.list_tunnels(
            cf_account_id=credentials.cf_account_id, api_token=credentials.api_token
        )
