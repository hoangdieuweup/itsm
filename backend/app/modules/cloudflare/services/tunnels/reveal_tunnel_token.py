"""Reveal a Tunnel's connector token: always re-fetch live from Cloudflare,
never from storage (Decision #8 — nothing is ever persisted to reveal).
Decision #6: gated at EDITOR, not OWNER, in the router — this token only
authorizes running cloudflared for ONE tunnel, a narrower blast radius than
an account's own api_token."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, CloudflareTunnelNotFound
from app.modules.cloudflare.rules import TunnelOwnershipRules
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead


class RevealCloudflareTunnelToken(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, tunnel_id: UUID, *, actor: UserRead) -> str:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or not TunnelOwnershipRules.verify_tunnel_belongs_to_account(
            tunnel, config.cloudflare_account_id
        ):
            raise CloudflareTunnelNotFound()

        credentials = await self._uow.accounts.get_credentials(config.cloudflare_account_id)
        if credentials is None:
            raise CloudflareConfigNotFound()

        token = await self._client.get_tunnel_token(
            cf_account_id=credentials.cf_account_id,
            cf_tunnel_id=tunnel.cf_tunnel_id,
            api_token=credentials.api_token,
        )

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_TOKEN_REVEALED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare Tunnel '{tunnel.name}' connector token revealed",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return token
