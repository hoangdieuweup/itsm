"""Delete an alert rule. CLOUDFLARE_NATIVE: call Cloudflare's delete_policy
first when a cf_policy_id was persisted — "external system first" convention,
same as every other Cloudflare-write use case. LOKI_QUERY rules have no
compensating Ruler-group delete in this cut (out of scope per the Phase 9
plan — accepted, disclosed limitation, not an oversight)."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.public import CloudflareApi
from app.modules.observability.constants import AlertingAuditActions, AlertRuleSource
from app.modules.observability.exceptions import AlertRuleNotFound
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.users.public import UserRead


class DeleteAlertRule(AbstractUseCase):
    def __init__(
        self, uow: AbstractObservabilityUnitOfWork, cloudflare_api: CloudflareApi, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._cloudflare_api = cloudflare_api
        self._audit_api = audit_api

    @use_case
    async def execute(self, alert_rule_id: UUID, *, actor: UserRead) -> None:
        existing = await self._uow.alert_rules.get_by_id(alert_rule_id)
        if existing is None:
            raise AlertRuleNotFound()

        if existing.source == AlertRuleSource.CLOUDFLARE_NATIVE and existing.cf_policy_id is not None:
            ready = await self._cloudflare_api.get_ready_client_for_environment(existing.environment_id)
            if ready is not None:
                await ready.client.delete_policy(
                    cf_account_id=ready.cf_account_id,
                    api_token=ready.api_token,
                    policy_id=existing.cf_policy_id,
                )

        await self._uow.alert_rules.delete(alert_rule_id)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=AlertingAuditActions.ALERT_RULE_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Alert rule '{existing.name}' deleted",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            environment_id=existing.environment_id,
        )
