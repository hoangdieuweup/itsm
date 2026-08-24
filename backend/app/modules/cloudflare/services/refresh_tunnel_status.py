"""Refresh a Tunnel's status on demand (Decision #10 — never automatic).
0 connections = DOWN, >=1 = HEALTHY. DEGRADED is never auto-set here — no
documented Cloudflare threshold exists for it."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import TunnelStatus
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, CloudflareTunnelNotFound
from app.modules.cloudflare.rules import TunnelOwnershipRules
from app.modules.cloudflare.schemas import CloudflareTunnelRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class RefreshTunnelStatus(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, environment_id: UUID, tunnel_id: UUID) -> CloudflareTunnelRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or not TunnelOwnershipRules.verify_tunnel_belongs_to_environment(
            tunnel, config.cloudflare_account_id
        ):
            raise CloudflareTunnelNotFound()

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        if account is None:
            raise CloudflareConfigNotFound()

        connections = await self._client.list_tunnel_connections(
            cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
        )
        status = TunnelStatus.HEALTHY if connections else TunnelStatus.DOWN

        updated = await self._uow.tunnels.update_status(
            tunnel_id, status=status, last_synced_at=datetime.now(UTC)
        )
        await self._uow.commit()
        return updated
