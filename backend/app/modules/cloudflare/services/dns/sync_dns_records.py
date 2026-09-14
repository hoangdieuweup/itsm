"""Sync DNS records from Cloudflare API into local DB for the zone bound to
an environment — matched per-record against every sibling environment
sharing that zone, not attributed wholesale to whichever environment
triggered the sync (see the "Bug Fix — DNS Record Environment Scoping" plan
section: `cloudflare_configs.zone_id` is not unique across environments, so
a shared zone's records were previously all claimed by the first environment
to ever sync it — the same class of bug fixed for Tunnels earlier).

On every page load the frontend still triggers this via one environment_id,
but the sync itself now:
1. Resolves that environment's bound Cloudflare zone.
2. Lists every environment currently bound to that SAME zone (siblings
   sharing it) — a sync from any one of them must never misattribute
   another's (or nobody's) records.
3. Fetches every record on the CF zone and, for EXTERNAL (dashboard-created)
   records, upserts each matched against the sibling environments' base_url
   (TunnelHostnameRules.match_environment_id — reused as-is, since a DNS
   record's `name` is the same shape of value a tunnel's ingress `hostname`
   is). SYSTEM (app-created) records keep the environment_id CreateDnsRecord
   gave them, never second-guessed by this heuristic.
4. Removes local-only records Cloudflare no longer reports for this zone.
5. Returns only the records actually attributed to the triggering environment.

Gracefully degrades — if the environment has no CF config, returns the
local list as-is without calling the API."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.core.base.markers import helper, use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.constants import ManagedBy
from app.modules.cloudflare.rules import DnsRecordSyncRules, TunnelHostnameRules
from app.modules.cloudflare.schemas import DnsRecordRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.projects.public import ProjectsApi

logger = logging.getLogger(__name__)


class SyncDnsRecords(AbstractUseCase):
    """Fetch every DNS record on the Cloudflare zone bound to
    environment_id, upsert them (matched to whichever sibling environment
    sharing the zone they actually belong to) into local DB, and remove
    local-only records Cloudflare no longer reports."""

    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, projects_api: ProjectsApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._projects_api = projects_api

    @use_case
    async def execute(self, environment_id: UUID) -> list[DnsRecordRead]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            return await self._uow.dns_records.list_for_environment(environment_id)

        credentials = await self._uow.accounts.get_credentials(config.cloudflare_account_id)
        if credentials is None:
            return await self._uow.dns_records.list_for_environment(environment_id)

        cf_records = await self._client.list_dns_records(
            zone_id=config.zone_id, api_token=credentials.api_token
        )

        cf_record_ids: set[str] = set()
        now = datetime.now(UTC)
        candidates = await self._resolve_sibling_environments(config.zone_id)

        for cf_rec in cf_records:
            cf_id = cf_rec["id"]
            cf_record_ids.add(cf_id)
            record_type = DnsRecordSyncRules.map_cf_type(cf_rec.get("type", ""))
            name = cf_rec.get("name", "")
            matched_environment_id = TunnelHostnameRules.match_environment_id(name, candidates)
            await self._uow.dns_records.upsert_from_sync(
                environment_id=matched_environment_id,
                cf_record_id=cf_id,
                record_type=record_type,
                name=name,
                content=cf_rec.get("content", ""),
                priority=cf_rec.get("priority"),
                proxied=cf_rec.get("proxied", False),
                ttl=cf_rec.get("ttl", 1),
                managed_by=ManagedBy.EXTERNAL,
                last_synced_at=now,
            )

        if cf_record_ids:
            sibling_environment_ids = [candidate_id for candidate_id, _ in candidates]
            await self._uow.dns_records.delete_not_in_cf_ids(sibling_environment_ids, cf_record_ids)

        await self._uow.commit()
        return await self._uow.dns_records.list_for_environment(environment_id)

    @helper
    async def _resolve_sibling_environments(self, zone_id: str) -> list[tuple[UUID, str | None]]:
        """Every environment bound to this zone, paired with its base_url —
        the candidate pool TunnelHostnameRules.match_environment_id matches
        each DNS record's name against."""
        sibling_ids = await self._uow.configs.list_environment_ids_for_zone(zone_id)
        candidates: list[tuple[UUID, str | None]] = []
        for sibling_id in sibling_ids:
            sibling = await self._projects_api.get_environment_by_id(sibling_id)
            if sibling is not None:
                candidates.append((sibling.id, sibling.base_url))
        return candidates
