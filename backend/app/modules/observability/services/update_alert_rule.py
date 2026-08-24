"""Update an alert rule's editable fields (name/is_active/severity/channels).
Does not re-sync source-specific external state (Cloudflare policy name,
Loki rule group) — those stay pinned to what was set at creation; only
delete+recreate changes them, matching how dns_records.record_type is
immutable after creation elsewhere in this codebase."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.observability.constants import AlertingAuditActions, AlertSeverity
from app.modules.observability.exceptions import AlertRuleNotFound
from app.modules.observability.schemas import AlertRuleRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.users.public import UserRead


class UpdateAlertRule(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        alert_rule_id: UUID,
        *,
        name: str | None = None,
        is_active: bool | None = None,
        severity: AlertSeverity | None = None,
        channel_ids: list[UUID] | None = None,
        actor: UserRead,
    ) -> AlertRuleRead:
        existing = await self._uow.alert_rules.get_by_id(alert_rule_id)
        if existing is None:
            raise AlertRuleNotFound()

        updated = await self._uow.alert_rules.update(
            alert_rule_id, name=name, is_active=is_active, severity=severity
        )
        if channel_ids is not None:
            await self._uow.alert_rules.set_channels(alert_rule_id, channel_ids)
            refetched = await self._uow.alert_rules.get_by_id(alert_rule_id)
            if refetched is None:
                raise AlertRuleNotFound()
            updated = refetched

        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=AlertingAuditActions.ALERT_RULE_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Alert rule '{updated.name}' updated",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            environment_id=updated.environment_id,
        )
        return updated
