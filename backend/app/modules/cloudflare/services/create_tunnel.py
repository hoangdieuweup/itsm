"""Create a Cloudflare Tunnel: call Cloudflare to create the tunnel, fetch
its one-time connector token, then persist the local row. Decision #8: the
token is never persisted — it's returned directly in this use case's result
and never stored anywhere; RevealCloudflareTunnelToken re-fetches it live
whenever it's needed again."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound
from app.modules.cloudflare.schemas import CloudflareTunnelRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead


class CreateCloudflareTunnel(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, name: str, *, actor: UserRead
    ) -> tuple[CloudflareTunnelRead, str]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        if account is None:
            raise CloudflareConfigNotFound()

        cf_tunnel_id = await self._client.create_tunnel(
            cf_account_id=account.cf_account_id, api_token=plaintext, name=name
        )
        token = await self._client.get_tunnel_token(
            cf_account_id=account.cf_account_id, cf_tunnel_id=cf_tunnel_id, api_token=plaintext
        )

        tunnel = await self._uow.tunnels.create(
            cloudflare_account_id=config.cloudflare_account_id, cf_tunnel_id=cf_tunnel_id, name=name
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare Tunnel '{name}' created",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return tunnel, token
