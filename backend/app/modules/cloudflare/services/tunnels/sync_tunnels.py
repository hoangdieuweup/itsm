"""Sync tunnels from Cloudflare API into local DB for the account bound to
an environment — account-wide, not environment-scoped (see Decision #3 in
the "Bug Fix — Cloudflare Tunnel Environment Scoping" plan section).

Tunnels are account-level resources: one tunnel commonly serves many
environments/projects at once through different public hostnames. The
previous, environment-scoped version of this use case upserted EVERY
tunnel in the account onto whichever environment triggered the sync,
silently reassigning the whole account's tunnel data on every page visit
(bugs/cloudflare-tunnel-ingress-and-project-environment-mapping.md).

On every page load the frontend still triggers this via one environment_id,
but the sync itself now:
1. Resolves that environment's bound Cloudflare account.
2. Lists every environment currently bound to that SAME account (siblings
   sharing the account) — a sync from any one of them must never corrupt
   another's data, so all siblings are matched in a single pass.
3. Fetches all tunnels from the CF account and upserts each keyed by
   cloudflare_account_id (tunnels are never keyed by environment_id again).
4. For each tunnel, pulls its REAL ingress config from Cloudflare
   (previously never fetched at all) and upserts every hostname, matching
   it against every sibling environment's base_url
   (TunnelHostnameRules.match_environment_id) — this is what populates
   tunnel_public_hostnames.environment_id and fixes the corruption.
5. Removes local hostnames Cloudflare no longer reports for that tunnel.
6. Marks local-only tunnels (deleted on CF) as DOWN.
7. Returns only the tunnels actually serving the triggering environment.

Gracefully degrades — if the environment has no CF config, returns the
local list as-is without calling the API."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.core.base.markers import helper, use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.rules import TunnelHostnameRules, TunnelSyncRules
from app.modules.cloudflare.schemas import CloudflareTunnelRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.projects.public import ProjectsApi

logger = logging.getLogger(__name__)


class SyncTunnels(AbstractUseCase):
    """Fetch every tunnel for the Cloudflare account bound to environment_id,
    upsert them (and their real ingress hostnames, matched to every sibling
    environment sharing the account) into local DB, and mark local-only
    tunnels as DOWN."""

    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, projects_api: ProjectsApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._projects_api = projects_api

    @use_case
    async def execute(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            return await self._uow.tunnels.list_for_environment_via_hostnames(environment_id)

        credentials = await self._uow.accounts.get_credentials(config.cloudflare_account_id)
        if credentials is None:
            return await self._uow.tunnels.list_for_environment_via_hostnames(environment_id)

        now = datetime.now(UTC)
        try:
            cf_tunnels = await self._client.list_tunnels(
                cf_account_id=credentials.cf_account_id, api_token=credentials.api_token
            )
        except Exception:
            logger.warning(
                "cloudflare list_tunnels failed for account %s; returning cached rows",
                credentials.account_id,
                exc_info=True,
            )
            return await self._uow.tunnels.list_for_environment_via_hostnames(environment_id)

        seen_cf_ids: set[str] = set()
        candidates = await self._resolve_sibling_environments(credentials.account_id)

        for cf_t in cf_tunnels:
            cf_tid = cf_t.get("id")
            name = cf_t.get("name")
            if not cf_tid or not name:
                continue
            seen_cf_ids.add(cf_tid)

            status = TunnelSyncRules.map_cf_status(cf_t.get("status", ""))

            tunnel = await self._uow.tunnels.upsert_from_sync(
                cloudflare_account_id=credentials.account_id,
                cf_tunnel_id=cf_tid,
                name=name,
                status=status,
                last_synced_at=now,
            )

            await self._sync_ingress(
                tunnel_id=tunnel.id,
                cf_account_id=credentials.cf_account_id,
                cf_tunnel_id=cf_tid,
                api_token=credentials.api_token,
                candidates=candidates,
                now=now,
            )

        await self._uow.tunnels.mark_missing_tunnels_down(
            cloudflare_account_id=credentials.account_id, active_cf_tunnel_ids=seen_cf_ids, synced_at=now
        )

        await self._uow.commit()
        return await self._uow.tunnels.list_for_environment_via_hostnames(environment_id)

    @helper
    async def _resolve_sibling_environments(
        self, cloudflare_account_id: UUID
    ) -> list[tuple[UUID, str | None]]:
        """Every environment bound to this account, paired with its
        base_url — the candidate pool TunnelHostnameRules.match_environment_id
        matches each ingress hostname against."""
        sibling_ids = await self._uow.configs.list_environment_ids_for_account(cloudflare_account_id)
        candidates: list[tuple[UUID, str | None]] = []
        for sibling_id in sibling_ids:
            sibling = await self._projects_api.get_environment_by_id(sibling_id)
            if sibling is not None:
                candidates.append((sibling.id, sibling.base_url))
        return candidates

    @helper
    async def _sync_ingress(
        self,
        *,
        tunnel_id: UUID,
        cf_account_id: str,
        cf_tunnel_id: str,
        api_token: str,
        candidates: list[tuple[UUID, str | None]],
        now: datetime,
    ) -> None:
        """Pull a tunnel's real ingress rules from Cloudflare and upsert
        each as a hostname row, matched to whichever sibling environment's
        base_url it corresponds to (or None if none match)."""
        ingress = await self._client.get_tunnel_configuration(
            cf_account_id=cf_account_id,
            cf_tunnel_id=cf_tunnel_id,
            api_token=api_token,
        )
        hostnames: set[str] = set()
        for ingress_rule in ingress:
            hostname = ingress_rule.get("hostname")
            if not hostname:
                continue
            hostnames.add(hostname)
            matched_environment_id = TunnelHostnameRules.match_environment_id(hostname, candidates)
            await self._uow.tunnel_hostnames.upsert_from_sync(
                tunnel_id=tunnel_id,
                hostname=hostname,
                service=ingress_rule.get("service", ""),
                environment_id=matched_environment_id,
                last_synced_at=now,
            )
        await self._uow.tunnel_hostnames.delete_not_in_hostnames(tunnel_id, hostnames)
