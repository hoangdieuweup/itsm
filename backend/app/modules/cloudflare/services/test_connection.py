"""Re-verify an already-saved Cloudflare account's token is still accepted."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class TestCloudflareAccountConnection(AbstractUseCase):
    """Re-run the same connectivity check CreateCloudflareAccount runs at
    entry time, using the account's already-stored (decrypted here) token —
    surfaced as a manual "Test Connection" button so a user can re-verify a
    token hasn't since been revoked on Cloudflare's side."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID) -> None:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        await self._client.test_connection(cf_account_id=account.cf_account_id, api_token=plaintext)
