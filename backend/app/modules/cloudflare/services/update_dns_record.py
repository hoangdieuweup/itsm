"""Update a DNS record: call Cloudflare first, persist locally only on
confirmation. Decision #3: captures the record's pre-update field values
before calling Cloudflare, so a local-write failure after Cloudflare's PATCH
succeeded can attempt a compensating PATCH back to those captured values."""

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
from app.modules.cloudflare.rules import CloudflareDnsRules
from app.modules.cloudflare.schemas import DnsRecordRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class UpdateDnsRecord(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        environment_id: UUID,
        record_id: UUID,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        *,
        actor: UserRead,
    ) -> DnsRecordRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        existing = await self._uow.dns_records.get_by_id(record_id)
        if existing is None or existing.environment_id != environment_id:
            raise DnsRecordNotFound()

        normalized_priority = CloudflareDnsRules.normalize_priority(existing.record_type, priority)
        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        await self._client.update_dns_record(
            zone_id=config.zone_id,
            cf_record_id=existing.cf_record_id,
            api_token=plaintext,
            record_type=existing.record_type,
            name=existing.name,
            content=content,
            priority=normalized_priority,
            proxied=proxied,
            ttl=ttl,
        )

        try:
            record = await self._uow.dns_records.update(
                record_id, content=content, priority=normalized_priority, proxied=proxied, ttl=ttl
            )
            await self._uow.commit()
        except Exception:
            logger.critical(
                "Local DNS record update failed after Cloudflare PATCH succeeded — attempting "
                "compensating revert (zone_id=%s, cf_record_id=%s)",
                config.zone_id,
                existing.cf_record_id,
                exc_info=True,
            )
            try:
                await self._client.update_dns_record(
                    zone_id=config.zone_id,
                    cf_record_id=existing.cf_record_id,
                    api_token=plaintext,
                    record_type=existing.record_type,
                    name=existing.name,
                    content=existing.content,
                    priority=existing.priority,
                    proxied=existing.proxied,
                    ttl=existing.ttl,
                )
                logger.critical("Compensating revert succeeded (cf_record_id=%s)", existing.cf_record_id)
            except Exception:
                logger.critical(
                    "Cloudflare/local state now DIVERGED — compensating revert ALSO failed, manual "
                    "reconciliation required (zone_id=%s, cf_record_id=%s)",
                    config.zone_id,
                    existing.cf_record_id,
                    exc_info=True,
                )
            raise DnsRecordSyncFailed() from None

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.DNS_RECORD_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"DNS record '{existing.name}' updated",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return record
