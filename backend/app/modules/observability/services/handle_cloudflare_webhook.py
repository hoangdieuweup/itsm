"""Receives a real Cloudflare Notifications webhook call. Verified live
against developers.cloudflare.com/notifications/reference/webhook-payload-schema/
(Decision #4): policy_id is the deterministic join key to alert_rules.
Only ALERT_STATE_EVENT_START creates anything; resolution stays a human
action via the ack/resolve endpoints. Deduped by alert_correlation_id
against any non-RESOLVED incident."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.public import NotificationsApi
from app.modules.observability.constants import AlertingAuditActions, AlertingLimits, IncidentSource
from app.modules.observability.exceptions import ObservabilityEnvironmentNotFound
from app.modules.observability.rules import AlertingRules
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi

logger = logging.getLogger(__name__)

_SYSTEM_ACTOR = AuditActor(user_id=None, email=None)


class HandleCloudflareWebhook(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractObservabilityUnitOfWork,
        *,
        notifications_api: NotificationsApi,
        projects_api: ProjectsApi,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._notifications_api = notifications_api
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(self, *, cloudflare_account_id: UUID, payload: dict) -> None:
        if payload.get("alert_event") != "ALERT_STATE_EVENT_START":
            return

        policy_id = payload.get("policy_id")
        rule = await self._uow.alert_rules.get_by_cf_policy_id(policy_id) if policy_id else None
        if rule is None:
            logger.warning("cloudflare webhook: no alert_rules row for policy_id=%s", policy_id)
            return

        correlation_id = payload.get("alert_correlation_id")
        if correlation_id and await self._uow.incidents.get_open_by_correlation_id(correlation_id):
            return

        environment = await self._projects_api.get_environment_by_id(rule.environment_id)
        if environment is None:
            raise ObservabilityEnvironmentNotFound()
        category = AlertingRules.category_for_cloudflare_alert_type(payload.get("alert_type", ""))
        title = (payload.get("text") or "Cloudflare alert")[: AlertingLimits.MAX_TITLE_LENGTH]

        incident = await self._uow.incidents.create(
            project_id=environment.project_id,
            environment_id=rule.environment_id,
            alert_rule_id=rule.id,
            source=IncidentSource.CLOUDFLARE,
            category=category,
            severity=rule.severity,
            title=title,
            alert_correlation_id=correlation_id,
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.INCIDENT_DETECTION,
            source=AuditSource.CLOUDFLARE,
            action=AlertingAuditActions.INCIDENT_DETECTED,
            severity=AuditSeverity.HIGH,
            message=title,
            actor=_SYSTEM_ACTOR,
            project_id=incident.project_id,
            environment_id=incident.environment_id,
            incident_id=str(incident.id),
        )
        await self._fan_out(rule.id, incident.id, title)

    async def _fan_out(self, alert_rule_id: UUID, incident_id: UUID, message: str) -> None:
        channel_ids = await self._uow.alert_rules.list_channel_ids(alert_rule_id)
        for channel_id in channel_ids:
            try:
                await self._notifications_api.dispatch(channel_id, message)
                status = "sent"
            except Exception:  # noqa: BLE001 -- a broken channel must never block incident creation, Decision #7
                logger.warning("notification dispatch failed for channel %s", channel_id, exc_info=True)
                status = "failed"
            await self._audit_api.log_event(
                type=AuditEventType.NOTIFICATION_SENT,
                source=AuditSource.SYSTEM,
                action=AlertingAuditActions.INCIDENT_NOTIFICATION_SENT,
                severity=AuditSeverity.INFO,
                message=f"Notification {status} for channel {channel_id}",
                actor=_SYSTEM_ACTOR,
                incident_id=str(incident_id),
            )
