"""Add a public hostname to a Tunnel's ingress array. This is a
GET-modify-PUT on a resource Cloudflare only exposes as a single
overwritable array (no per-rule endpoint), so the whole operation is
wrapped in a short Redis lock to prevent two concurrent editors from
clobbering each other (Decision #1: reject immediately, never poll-and-wait).

Decision #2: the array is always reconstructed from a FRESH GET, never from
DB rows — this is the only way to avoid silently dropping fields this app
doesn't model (path, originRequest, ...) on rules it isn't touching.

Decision #4: a rule is "catch-all" iff it has no hostname key, or that key
is None. New named rules are inserted before any catch-all rule(s)."""

import logging
from uuid import UUID

from app.core.base.markers import helper, use_case
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
    TunnelHostnameAlreadyExists,
    TunnelHostnameDomainMismatch,
    TunnelHostnameEnvironmentMismatch,
    TunnelIngressSyncFailed,
)
from app.modules.cloudflare.rules import TunnelHostnameRules, TunnelOwnershipRules
from app.modules.cloudflare.schemas import TunnelPublicHostnameRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class AddTunnelHostname(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractCloudflareUnitOfWork,
        client: CloudflareClient,
        cache: CacheClient,
        audit_api: AuditApi,
        projects_api: ProjectsApi,
    ) -> None:
        self._uow = uow
        self._client = client
        self._cache = cache
        self._audit_api = audit_api
        self._projects_api = projects_api

    @staticmethod
    @helper
    def _is_catch_all(rule: dict) -> bool:
        return "hostname" not in rule or rule.get("hostname") is None

    @helper
    async def _resolve_sibling_environments(
        self, cloudflare_account_id: UUID
    ) -> list[tuple[UUID, str | None]]:
        """Every environment bound to this account, paired with its
        base_url — mirrors SyncTunnels' own helper of the same name."""
        sibling_ids = await self._uow.configs.list_environment_ids_for_account(cloudflare_account_id)
        candidates: list[tuple[UUID, str | None]] = []
        for sibling_id in sibling_ids:
            sibling = await self._projects_api.get_environment_by_id(sibling_id)
            if sibling is not None:
                candidates.append((sibling.id, sibling.base_url))
        return candidates

    @use_case
    async def execute(
        self, environment_id: UUID, tunnel_id: UUID, hostname: str, service: str, *, actor: UserRead
    ) -> TunnelPublicHostnameRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        if not TunnelHostnameRules.belongs_to_zone(hostname, config.zone_name):
            raise TunnelHostnameDomainMismatch()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or not TunnelOwnershipRules.verify_tunnel_belongs_to_account(
            tunnel, config.cloudflare_account_id
        ):
            raise CloudflareTunnelNotFound()
        existing_on_tunnel = await self._uow.tunnel_hostnames.list_for_tunnel(tunnel_id)
        if any(h.hostname == hostname for h in existing_on_tunnel):
            raise TunnelHostnameAlreadyExists()

        candidates = await self._resolve_sibling_environments(config.cloudflare_account_id)
        if TunnelHostnameRules.claims_another_environment(hostname, environment_id, candidates):
            raise TunnelHostnameEnvironmentMismatch()

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
            named_rules = [r for r in current_ingress if not self._is_catch_all(r)]
            catch_all = [r for r in current_ingress if self._is_catch_all(r)]
            new_rule = {"hostname": hostname, "service": service}
            new_ingress = [*named_rules, new_rule, *catch_all]

            await self._client.put_tunnel_configuration(
                cf_account_id=credentials.cf_account_id,
                cf_tunnel_id=tunnel.cf_tunnel_id,
                api_token=credentials.api_token,
                ingress=new_ingress,
            )

            try:
                created = await self._uow.tunnel_hostnames.create(
                    tunnel_id=tunnel_id,
                    hostname=hostname,
                    service=service,
                    created_by=actor.id,
                    environment_id=environment_id,
                )
                await self._uow.commit()
            except Exception:
                logger.critical(
                    "Local tunnel hostname write failed after Cloudflare PUT succeeded — attempting "
                    "compensating PUT-back (tunnel_id=%s, hostname=%s)",
                    tunnel_id,
                    hostname,
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
            action=CloudflareTunnelAuditActions.TUNNEL_HOSTNAME_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Tunnel hostname '{hostname}' added",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return created
