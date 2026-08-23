"""List an environment's Cloudflare Audit Log entries (config-change history,
not raw traffic — Logpull was dropped from Phase 6, Enterprise-plan only).
Mirrors ListZones' resolve-account-then-decrypt-token shape."""

from datetime import datetime
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.schemas import CloudflareAuditLogEntry
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound, CloudflareConfigNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListCloudflareAuditLogs(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(
        self, *, environment_id: UUID, since: datetime | None, before: datetime | None
    ) -> list[CloudflareAuditLogEntry]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()

        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareAccountNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        return await self._client.get_account_audit_logs(
            cf_account_id=account.cf_account_id,
            api_token=plaintext,
            zone_name=config.zone_name,
            since=since,
            before=before,
        )
