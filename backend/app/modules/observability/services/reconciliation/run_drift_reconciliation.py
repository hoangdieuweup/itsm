"""Periodic drift reconciliation — the spec's "second safety layer": since
Cloudflare has no way to block a user with dashboard access from creating
or deleting DNS records/Tunnel hostnames directly, this re-checks every
Cloudflare-bound environment's live state on a fixed interval and files an
incident whenever something changed outside this app. Driven by
app/scheduler.py, not by any HTTP route — there is no human actor.

DNS reconciliation runs once per bound environment (dns_records/
cloudflare_configs are genuinely 1:1 per environment). Tunnel
reconciliation runs once per distinct Cloudflare account (a tunnel serves
many environments at once — reconciling per-environment would either
redundantly re-sync the same account repeatedly or misattribute drift to
whichever environment happened to trigger the pass; see
CloudflareApi.reconcile_tunnels_for_account)."""

import logging
from uuid import UUID

from app.core.base.markers import helper, use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.public import CloudflareApi, DriftKind
from app.modules.observability.constants import (
    AlertingAuditActions,
    AlertingLimits,
    AlertSeverity,
    IncidentCategory,
    IncidentSource,
)
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi

logger = logging.getLogger(__name__)


class RunDriftReconciliation(AbstractUseCase):
    SYSTEM_ACTOR = AuditActor(user_id=None, email=None)

    def __init__(
        self,
        uow: AbstractObservabilityUnitOfWork,
        *,
        cloudflare_api: CloudflareApi,
        projects_api: ProjectsApi,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._cloudflare_api = cloudflare_api
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(self) -> None:
        configs = await self._cloudflare_api.list_bound_configs()

        for config in configs:
            try:
                await self._reconcile_dns(config.environment_id)
            except Exception:
                logger.exception(
                    "DNS drift reconciliation failed for environment_id=%s", config.environment_id
                )

        seen_account_ids: set[UUID] = set()
        for config in configs:
            if config.cloudflare_account_id in seen_account_ids:
                continue
            seen_account_ids.add(config.cloudflare_account_id)
            try:
                await self._reconcile_tunnels(config.cloudflare_account_id)
            except Exception:
                logger.exception(
                    "Tunnel drift reconciliation failed for cloudflare_account_id=%s",
                    config.cloudflare_account_id,
                )

    @helper
    async def _reconcile_dns(self, environment_id: UUID) -> None:
        diff = await self._cloudflare_api.reconcile_dns_records(environment_id)
        for record in diff.new_external:
            await self._raise_incident(
                environment_id=environment_id,
                category=IncidentCategory.DNS_DRIFT,
                severity=AlertSeverity.HIGH,
                title=f"New DNS record discovered outside the system: {record.name} ({record.record_type})",
                correlation_id=f"dns_drift:{record.cf_record_id}",
                action=AlertingAuditActions.DNS_DRIFT_DETECTED,
            )
        for record in diff.vanished:
            await self._raise_incident(
                environment_id=environment_id,
                category=IncidentCategory.DNS_DRIFT,
                severity=AlertSeverity.LOW,
                title=f"DNS record removed outside the system: {record.name} ({record.record_type})",
                correlation_id=f"dns_drift:{record.cf_record_id}",
                action=AlertingAuditActions.DNS_DRIFT_DETECTED,
            )

    @helper
    async def _reconcile_tunnels(self, cloudflare_account_id: UUID) -> None:
        entries = await self._cloudflare_api.reconcile_tunnels_for_account(cloudflare_account_id)
        for entry in entries:
            is_new = entry.kind == DriftKind.NEW_EXTERNAL
            await self._raise_incident(
                environment_id=entry.environment_id,
                category=IncidentCategory.TUNNEL_DRIFT,
                severity=AlertSeverity.HIGH if is_new else AlertSeverity.LOW,
                title=(
                    f"Tunnel hostname {'discovered' if is_new else 'removed'} outside the system: "
                    f"{entry.hostname.hostname}"
                ),
                correlation_id=f"tunnel_drift:{entry.hostname.hostname}",
                action=AlertingAuditActions.TUNNEL_DRIFT_DETECTED,
            )

    @helper
    async def _raise_incident(
        self,
        *,
        environment_id: UUID,
        category: IncidentCategory,
        severity: AlertSeverity,
        title: str,
        correlation_id: str,
        action: AlertingAuditActions,
    ) -> None:
        """Deduped via the same get_open_by_correlation_id guard the webhook
        receivers already use — without it, a still-unresolved drift would
        spawn a fresh incident every reconciliation pass, forever. A
        RESOLVED incident with the same correlation id does not block a new
        one: resolving the incident isn't the same as fixing the drift."""
        if await self._uow.incidents.get_open_by_correlation_id(correlation_id):
            return
        environment = await self._projects_api.get_environment_by_id(environment_id)
        if environment is None:
            logger.warning(
                "drift reconciliation: environment %s no longer exists, skipping incident", environment_id
            )
            return

        incident = await self._uow.incidents.create(
            project_id=environment.project_id,
            environment_id=environment_id,
            alert_rule_id=None,
            source=IncidentSource.CLOUDFLARE,
            category=category,
            severity=severity,
            title=title[: AlertingLimits.MAX_TITLE_LENGTH],
            alert_correlation_id=correlation_id,
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.INCIDENT_DETECTION,
            source=AuditSource.CLOUDFLARE,
            action=action,
            severity=AuditSeverity(severity.value),
            message=title,
            actor=self.SYSTEM_ACTOR,
            project_id=incident.project_id,
            environment_id=incident.environment_id,
            incident_id=str(incident.id),
        )
