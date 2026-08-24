"""Receives an Alertmanager webhook_config POST — the standard Prometheus
Alertmanager contract, not documented anywhere in this repo's own spec docs
(Decision #11). Joins back to alert_rules via labels.app_alert_rule_id
(set by upsert_rule_group at rule-creation time). Dedupes by Alertmanager's
own fingerprint. Only status=="firing" entries are processed — a batch may
contain several alerts, each handled independently; one bad entry never
aborts the rest."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.public import NotificationsApi
from app.modules.observability.constants import (
    AlertingAuditActions,
    AlertingLimits,
    IncidentCategory,
    IncidentSource,
)
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi

logger = logging.getLogger(__name__)
_SYSTEM_ACTOR = AuditActor(user_id=None, email=None)


class HandleLokiWebhook(AbstractUseCase):
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
    async def execute(self, payload: dict) -> None:
        for alert in payload.get("alerts", []):
            if alert.get("status") != "firing":
                continue
            await self._handle_one(alert)

    async def _handle_one(self, alert: dict) -> None:
        labels = alert.get("labels", {})
        raw_rule_id = labels.get("app_alert_rule_id")
        rule = None
        if raw_rule_id:
            try:
                rule = await self._uow.alert_rules.get_by_id(UUID(raw_rule_id))
            except ValueError:
                rule = None
        if rule is None:
            logger.warning("loki webhook: no alert_rules row for app_alert_rule_id=%s", raw_rule_id)
            return

        fingerprint = alert.get("fingerprint")
        if fingerprint and await self._uow.incidents.get_open_by_correlation_id(fingerprint):
            return

        environment = await self._projects_api.get_environment_by_id(rule.environment_id)
        if environment is None:
            logger.warning("loki webhook: environment %s no longer exists", rule.environment_id)
            return
        title = (alert.get("annotations", {}).get("summary") or labels.get("alertname") or "Loki alert")[
            : AlertingLimits.MAX_TITLE_LENGTH
        ]
        incident = await self._uow.incidents.create(
            project_id=environment.project_id,
            environment_id=rule.environment_id,
            alert_rule_id=rule.id,
            source=IncidentSource.LOKI,
            category=IncidentCategory.LOG_MATCH,
            severity=rule.severity,
            title=title,
            alert_correlation_id=fingerprint,
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.INCIDENT_DETECTION,
            source=AuditSource.LOKI,
            action=AlertingAuditActions.INCIDENT_DETECTED,
            severity=AuditSeverity.HIGH,
            message=title,
            actor=_SYSTEM_ACTOR,
            project_id=incident.project_id,
            environment_id=incident.environment_id,
            incident_id=str(incident.id),
        )
        for channel_id in await self._uow.alert_rules.list_channel_ids(rule.id):
            try:
                await self._notifications_api.dispatch(channel_id, title)
                status = "sent"
            except Exception:  # noqa: BLE001 -- same Decision #7 reasoning as the Cloudflare path
                logger.warning("notification dispatch failed for channel %s", channel_id, exc_info=True)
                status = "failed"
            await self._audit_api.log_event(
                type=AuditEventType.NOTIFICATION_SENT,
                source=AuditSource.SYSTEM,
                action=AlertingAuditActions.INCIDENT_NOTIFICATION_SENT,
                severity=AuditSeverity.INFO,
                message=f"Notification {status} for channel {channel_id}",
                actor=_SYSTEM_ACTOR,
                incident_id=str(incident.id),
            )
