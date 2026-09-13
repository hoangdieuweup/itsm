"""Create a DNS record: call Cloudflare first, persist locally only on
confirmation. Decision #3: if the local write then fails, attempt a
compensating delete back to Cloudflare rather than leaving an orphaned
record with zero local trace — a dns_records row is primary state, not
audit's secondary observation, so failure here must surface loudly."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareDnsAuditActions, DnsRecordType
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, DnsRecordSyncFailed
from app.modules.cloudflare.rules import CloudflareDnsRules
from app.modules.cloudflare.schemas import DnsRecordRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class CreateDnsRecord(AbstractUseCase):
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
        record_type: DnsRecordType,
        name: str,
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

        normalized_priority = CloudflareDnsRules.normalize_priority(record_type, priority)

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        cf_record_id = await self._client.create_dns_record(
            zone_id=config.zone_id,
            api_token=plaintext,
            record_type=record_type,
            name=name,
            content=content,
            priority=normalized_priority,
            proxied=proxied,
            ttl=ttl,
        )

        try:
            record = await self._uow.dns_records.create(
                environment_id=environment_id,
                cf_record_id=cf_record_id,
                record_type=record_type,
                name=name,
                content=content,
                priority=normalized_priority,
                proxied=proxied,
                ttl=ttl,
                created_by=actor.id,
            )
            await self._uow.commit()
        except Exception:
            logger.critical(
                "Local DNS record write failed after Cloudflare create succeeded — attempting "
                "compensating delete (zone_id=%s, cf_record_id=%s)",
                config.zone_id,
                cf_record_id,
                exc_info=True,
            )
            try:
                await self._client.delete_dns_record(
                    zone_id=config.zone_id, cf_record_id=cf_record_id, api_token=plaintext
                )
                logger.critical(
                    "Compensating delete succeeded — orphan avoided (cf_record_id=%s)", cf_record_id
                )
            except Exception:
                logger.critical(
                    "ORPHAN DNS RECORD on Cloudflare — compensating delete ALSO failed, manual "
                    "cleanup required (zone_id=%s, cf_record_id=%s)",
                    config.zone_id,
                    cf_record_id,
                    exc_info=True,
                )
            raise DnsRecordSyncFailed() from None

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.DNS_RECORD_CREATED,
            severity=AuditSeverity.INFO,
            message=f"DNS record '{name}' ({record_type}) created",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return record
