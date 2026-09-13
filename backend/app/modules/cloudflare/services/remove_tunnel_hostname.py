"""Remove a public hostname from a Tunnel's ingress array. Same lock +
fresh-GET + splice shape as AddTunnelHostname — see that module's docstring.

Unlike DeleteDnsRecord (no compensating action possible once a real DNS
record is gone), a compensating PUT-back IS possible here: the pre-removal
ingress array was captured before the mutating PUT, so it can always be
best-effort restored on a subsequent local-delete failure (Decision #5).

Risk (documented, not solved here): if the removed rule was the only rule
and no catch-all exists, the resulting array would violate Cloudflare's own
minItems:1 — that PUT is rejected by Cloudflare itself (surfaces as a normal
CloudflareDnsOperationRejected, not a sync-failure, since it happens before
any local mutation), not silently accepted."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions, CloudflareTunnelLockDefaults
from app.modules.cloudflare.exceptions import (
    CloudflareConfigNotFound,
    CloudflareTunnelNotFound,
    TunnelConfigLocked,
    TunnelIngressSyncFailed,
    TunnelPublicHostnameNotFound,
)
from app.modules.cloudflare.rules import TunnelOwnershipRules
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class RemoveTunnelHostname(AbstractUseCase):
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
        self, environment_id: UUID, tunnel_id: UUID, hostname_id: UUID, *, actor: UserRead
    ) -> None:
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
            ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
            if ciphertext is None:
                raise CloudflareConfigNotFound()
            plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
            account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
            if account is None:
                raise CloudflareConfigNotFound()

            current_ingress = await self._client.get_tunnel_configuration(
                cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
            )
            new_ingress = [rule for rule in current_ingress if rule.get("hostname") != existing.hostname]

            await self._client.put_tunnel_configuration(
                cf_account_id=account.cf_account_id,
                cf_tunnel_id=tunnel.cf_tunnel_id,
                api_token=plaintext,
                ingress=new_ingress,
            )

            try:
                await self._uow.tunnel_hostnames.delete(hostname_id)
                await self._uow.commit()
            except Exception:
                logger.critical(
                    "Local tunnel hostname delete failed after Cloudflare PUT succeeded — attempting "
                    "compensating PUT-back (tunnel_id=%s, hostname_id=%s)",
                    tunnel_id,
                    hostname_id,
                    exc_info=True,
                )
                try:
                    await self._client.put_tunnel_configuration(
                        cf_account_id=account.cf_account_id,
                        cf_tunnel_id=tunnel.cf_tunnel_id,
                        api_token=plaintext,
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
            action=CloudflareTunnelAuditActions.TUNNEL_HOSTNAME_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Tunnel hostname '{existing.hostname}' removed",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
