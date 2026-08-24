"""Sync DNS records from Cloudflare API into local DB for an environment.

On every page load the frontend triggers this use case, which:
1. Fetches all DNS records from the CF zone bound to this environment.
2. Upserts each into local DB (insert new as EXTERNAL, update existing).
3. Removes local-only records (deleted on CF) from the DB.
4. Returns the fresh record list.

Gracefully degrades — if the environment has no CF config, returns the
local list as-is without calling the API."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.core.base.markers import rule, use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import DnsRecordType, ManagedBy
from app.modules.cloudflare.schemas import DnsRecordRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork

logger = logging.getLogger(__name__)


class DnsRecordSyncRules:
    """Pure mapping rules for Cloudflare → local DNS record type."""

    _CF_TYPE_MAP: dict[str, DnsRecordType] = {
        "A": DnsRecordType.A,
        "AAAA": DnsRecordType.AAAA,
        "CNAME": DnsRecordType.CNAME,
        "TXT": DnsRecordType.TXT,
        "MX": DnsRecordType.MX,
    }

    @staticmethod
    @rule
    def map_cf_type(cf_type: str) -> DnsRecordType:
        """Map a Cloudflare API record type string to local DnsRecordType enum."""
        return DnsRecordSyncRules._CF_TYPE_MAP.get(cf_type, DnsRecordType.OTHER)


class SyncDnsRecords(AbstractUseCase):
    """Fetch all DNS records from Cloudflare API for this environment's zone,
    upsert them into local DB, and remove stale local records."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, environment_id: UUID) -> list[DnsRecordRead]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            return await self._uow.dns_records.list_for_environment(environment_id)

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            return await self._uow.dns_records.list_for_environment(environment_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        cf_records = await self._client.list_dns_records(
            zone_id=config.zone_id,
            api_token=plaintext,
        )

        cf_record_ids: set[str] = set()
        now = datetime.now(UTC)
        for cf_rec in cf_records:
            cf_id = cf_rec["id"]
            cf_record_ids.add(cf_id)
            record_type = DnsRecordSyncRules.map_cf_type(cf_rec.get("type", ""))
            await self._uow.dns_records.upsert_from_sync(
                environment_id=environment_id,
                cf_record_id=cf_id,
                record_type=record_type,
                name=cf_rec.get("name", ""),
                content=cf_rec.get("content", ""),
                priority=cf_rec.get("priority"),
                proxied=cf_rec.get("proxied", False),
                ttl=cf_rec.get("ttl", 1),
                managed_by=ManagedBy.EXTERNAL,
                last_synced_at=now,
            )

        if cf_record_ids:
            await self._uow.dns_records.delete_not_in_cf_ids(environment_id, cf_record_ids)

        await self._uow.commit()
        return await self._uow.dns_records.list_for_environment(environment_id)
