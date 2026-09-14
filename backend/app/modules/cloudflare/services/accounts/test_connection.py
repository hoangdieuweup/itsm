"""Re-verify an already-saved Cloudflare account's token is still accepted."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class TestCloudflareAccountConnection(AbstractUseCase):
    """Re-run the same connectivity check CreateCloudflareAccount runs at
    entry time, using the account's already-stored (decrypted here) token —
    surfaced as a manual "Test Connection" button so a user can re-verify a
    token hasn't since been revoked on Cloudflare's side."""

    __test__ = False

    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID) -> None:
        credentials = await self._uow.accounts.get_credentials(account_id)
        if credentials is None:
            raise CloudflareAccountNotFound()
        await self._client.test_connection(
            cf_account_id=credentials.cf_account_id, api_token=credentials.api_token
        )
