"""Rebind an environment to a different zone on the same account. Cloudflare
verifies zone ownership before persisting, same principle as create_config.py."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import (
    CloudflareAccountNotFound,
    CloudflareConfigNotFound,
    ZoneNotOwnedByAccount,
)
from app.modules.cloudflare.schemas import CloudflareConfigRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class UpdateCloudflareConfig(AbstractUseCase):
    """Router gates this with require_account_access_for_environment(EDITOR)
    directly — no request-body-dependent decision, so actor identity is
    passed as plain actor_id/actor_email (matches DeleteCloudflareAccount's
    simpler shape), not threaded through the grant object."""

    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, zone_id: str, *, actor_id: UUID, actor_email: str
    ) -> CloudflareConfigRead:
        existing = await self._uow.configs.get_by_environment_id(environment_id)
        if existing is None:
            raise CloudflareConfigNotFound()

        account = await self._uow.accounts.get_by_id(existing.cloudflare_account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(existing.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareAccountNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        zones = await self._client.list_zones(cf_account_id=account.cf_account_id, api_token=plaintext)
        matched = next((z for z in zones if z.id == zone_id), None)
        if matched is None:
            raise ZoneNotOwnedByAccount()

        config = await self._uow.configs.update_by_environment_id(
            environment_id,
            cloudflare_account_id=existing.cloudflare_account_id,
            zone_id=zone_id,
            zone_name=matched.name,
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.CONFIG_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Environment rebound to Cloudflare zone '{matched.name}'",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return config
