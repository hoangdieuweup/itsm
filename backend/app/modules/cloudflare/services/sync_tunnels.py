"""Sync tunnels from Cloudflare API into local DB for an environment.

On every page load the frontend triggers this use case, which:
1. Fetches all tunnels from the CF account bound to this environment.
2. Upserts each into local DB (insert new, update name/status for existing).
3. Marks local-only tunnels (deleted on CF) as DOWN.
4. Returns the fresh tunnel list.

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
from app.modules.cloudflare.constants import TunnelStatus
from app.modules.cloudflare.schemas import CloudflareTunnelRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork

logger = logging.getLogger(__name__)


class TunnelSyncRules:
    """Pure mapping rules for Cloudflare → local tunnel status."""

    _CF_STATUS_MAP: dict[str, TunnelStatus] = {
        "healthy": TunnelStatus.HEALTHY,
        "degraded": TunnelStatus.DEGRADED,
        "down": TunnelStatus.DOWN,
        "inactive": TunnelStatus.UNKNOWN,
    }

    @staticmethod
    @rule
    def map_cf_status(cf_status: str) -> TunnelStatus:
        """Map a Cloudflare API status string to local TunnelStatus enum."""
        return TunnelSyncRules._CF_STATUS_MAP.get(cf_status, TunnelStatus.UNKNOWN)


class SyncTunnels(AbstractUseCase):
    """Fetch all tunnels from Cloudflare API for this environment's account,
    upsert them into local DB, and mark local-only tunnels as DOWN."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            return await self._uow.tunnels.list_for_environment(environment_id)

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            return await self._uow.tunnels.list_for_environment(environment_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        if account is None:
            return await self._uow.tunnels.list_for_environment(environment_id)

        cf_tunnels = await self._client.list_tunnels(
            cf_account_id=account.cf_account_id, api_token=plaintext,
        )

        cf_tunnel_ids: set[str] = set()
        now = datetime.now(UTC)
        for cf_t in cf_tunnels:
            cf_id = cf_t["id"]
            cf_tunnel_ids.add(cf_id)
            status = TunnelSyncRules.map_cf_status(cf_t.get("status", ""))
            await self._uow.tunnels.upsert_from_sync(
                environment_id=environment_id,
                cf_tunnel_id=cf_id,
                name=cf_t.get("name") or cf_id,
                status=status,
                last_synced_at=now,
            )

        local_tunnels = await self._uow.tunnels.list_for_environment(environment_id)
        for lt in local_tunnels:
            if lt.cf_tunnel_id not in cf_tunnel_ids:
                await self._uow.tunnels.update_status(
                    lt.id, status=TunnelStatus.DOWN, last_synced_at=now,
                )

        await self._uow.commit()
        return await self._uow.tunnels.list_for_environment(environment_id)
