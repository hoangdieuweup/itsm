"""Delete a Cloudflare Tunnel: call Cloudflare first, then delete locally.
Decision #7: no guard on existing tunnel_public_hostnames rows — unlike
DeleteCloudflareConfig, ON DELETE CASCADE handles them, since a tunnel's
hostnames belong to and are meant to disappear with it (they aren't
independent zone resources the way dns_records are)."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, CloudflareTunnelNotFound
from app.modules.cloudflare.rules import TunnelOwnershipRules
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead


class DeleteCloudflareTunnel(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, tunnel_id: UUID, *, actor: UserRead) -> None:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or not TunnelOwnershipRules.verify_tunnel_belongs_to_account(
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

        await self._client.delete_tunnel(
            cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
        )

        await self._uow.tunnels.delete(tunnel_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare Tunnel '{tunnel.name}' deleted",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
