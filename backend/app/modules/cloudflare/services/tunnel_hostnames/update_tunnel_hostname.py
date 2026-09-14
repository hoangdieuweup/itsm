"""Update a Tunnel hostname's service target. Same lock + fresh-GET +
splice + compensating-PUT-back shape as AddTunnelHostname — see that
module's docstring for the full rationale (Decisions #1-#5). hostname
itself is immutable; only `service` is replaced in place, preserving every
other field already on that rule (path, originRequest, ...)."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cache.client import CacheClient
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions, CloudflareTunnelLockDefaults
from app.modules.cloudflare.exceptions import (
    CloudflareConfigNotFound,
    CloudflareTunnelNotFound,
    TunnelConfigLocked,
    TunnelIngressSyncFailed,
    TunnelPublicHostnameNotFound,
)
from app.modules.cloudflare.rules import TunnelOwnershipRules
from app.modules.cloudflare.schemas import TunnelPublicHostnameRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class UpdateTunnelHostname(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractCloudflareUnitOfWork,
        client: CloudflareClient,
        cache: CacheClient,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._client = client
        self._cache = cache
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, tunnel_id: UUID, hostname_id: UUID, service: str, *, actor: UserRead
    ) -> TunnelPublicHostnameRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or not TunnelOwnershipRules.verify_tunnel_belongs_to_account(
            tunnel, config.cloudflare_account_id
        ):
            raise CloudflareTunnelNotFound()
        existing = await self._uow.tunnel_hostnames.get_by_id(hostname_id)
        if existing is None or existing.tunnel_id != tunnel_id or existing.environment_id != environment_id:
            raise TunnelPublicHostnameNotFound()

        lock_key = CacheKeyBuilder.lock_key("tunnel", tunnel_id)
        acquired = await self._cache.try_acquire_lock(
            lock_key, ttl=CloudflareTunnelLockDefaults.INGRESS_LOCK_TTL_SECONDS
        )
        if not acquired:
            raise TunnelConfigLocked()

        try:
            credentials = await self._uow.accounts.get_credentials(config.cloudflare_account_id)
            if credentials is None:
                raise CloudflareConfigNotFound()

            current_ingress = await self._client.get_tunnel_configuration(
                cf_account_id=credentials.cf_account_id,
                cf_tunnel_id=tunnel.cf_tunnel_id,
                api_token=credentials.api_token,
            )
            new_ingress = [
                {**rule, "service": service} if rule.get("hostname") == existing.hostname else rule
                for rule in current_ingress
            ]

            await self._client.put_tunnel_configuration(
                cf_account_id=credentials.cf_account_id,
                cf_tunnel_id=tunnel.cf_tunnel_id,
                api_token=credentials.api_token,
                ingress=new_ingress,
            )

            try:
                updated = await self._uow.tunnel_hostnames.update_service(hostname_id, service=service)
                await self._uow.commit()
            except Exception:
                logger.critical(
                    "Local tunnel hostname update failed after Cloudflare PUT succeeded — attempting "
                    "compensating PUT-back (tunnel_id=%s, hostname_id=%s)",
                    tunnel_id,
                    hostname_id,
                    exc_info=True,
                )
                try:
                    await self._client.put_tunnel_configuration(
                        cf_account_id=credentials.cf_account_id,
                        cf_tunnel_id=tunnel.cf_tunnel_id,
                        api_token=credentials.api_token,
                        ingress=current_ingress,
                    )
                    logger.critical("Compensating PUT-back succeeded (tunnel_id=%s)", tunnel_id)
                except Exception:
                    logger.critical(
                        "Compensating PUT-back ALSO failed — ingress may be out of sync, manual "
                        "reconciliation required (tunnel_id=%s)",
                        tunnel_id,
                        exc_info=True,
                    )
                raise TunnelIngressSyncFailed() from None
        finally:
            await self._cache.release_lock(lock_key)

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_HOSTNAME_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Tunnel hostname '{existing.hostname}' updated",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return updated
