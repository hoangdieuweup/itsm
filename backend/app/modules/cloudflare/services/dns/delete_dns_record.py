"""Delete a DNS record: call Cloudflare first, delete locally only on
confirmation. Decision #3: unlike create/update, NO compensating action is
possible here — once Cloudflare's DELETE succeeds the record is genuinely
gone. A local-delete failure after that can only be logged loudly and
surfaced as an error; the residual state-divergence gap is accepted until
Phase 10's reconciliation job exists."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, DnsRecordNotFound, DnsRecordSyncFailed
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class DeleteDnsRecord(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, record_id: UUID, *, actor: UserRead) -> None:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        existing = await self._uow.dns_records.get_by_id(record_id)
        if existing is None or existing.environment_id != environment_id:
            raise DnsRecordNotFound()

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        await self._client.delete_dns_record(
            zone_id=config.zone_id, cf_record_id=existing.cf_record_id, api_token=plaintext
        )

        try:
            await self._uow.dns_records.delete(record_id)
            await self._uow.commit()
        except Exception:
            logger.critical(
                "DNS record deleted on Cloudflare but local delete failed — no compensating action "
                "possible, state may have diverged (zone_id=%s, cf_record_id=%s, environment_id=%s)",
                config.zone_id,
                existing.cf_record_id,
                environment_id,
                exc_info=True,
            )
            raise DnsRecordSyncFailed() from None

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.DNS_RECORD_DELETED,
            severity=AuditSeverity.INFO,
            message=f"DNS record '{existing.name}' deleted",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
