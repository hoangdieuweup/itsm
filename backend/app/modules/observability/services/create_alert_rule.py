"""Create an alert rule. CLOUDFLARE_NATIVE: resolve the environment's bound
Cloudflare account -> ensure a webhook destination exists for it -> create
the Notification Policy -> persist with the real cf_policy_id (Decision #9).
LOKI_QUERY: push the rule into Loki's own Ruler so it actually gets
evaluated (Decision #10) — storing it in our DB alone would never cause
Loki to fire anything. Nothing persists locally until the external call
that source needs has already succeeded, mirroring the "call the external
system first" convention every prior Cloudflare-write use case follows."""

from uuid import UUID

from app.config import settings as root_settings
from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.public import CloudflareApi
from app.modules.observability.constants import AlertingAuditActions, AlertRuleSource, AlertSeverity
from app.modules.observability.exceptions import (
    AlertRuleNotFound,
    CloudflareNotBoundForAlerting,
    MissingCloudflareAlertType,
    ObservabilityEnvironmentNotFound,
)
from app.modules.observability.schemas import AlertRuleRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead


class CreateAlertRule(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractObservabilityUnitOfWork,
        *,
        cloudflare_api: CloudflareApi | None,
        loki_client,
        projects_api: ProjectsApi,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._cloudflare_api = cloudflare_api
        self._loki_client = loki_client
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        *,
        environment_id: UUID,
        name: str,
        source: AlertRuleSource,
        cf_alert_type: str | None,
        condition: dict | None,
        severity: AlertSeverity,
        channel_ids: list[UUID],
        actor: UserRead,
    ) -> AlertRuleRead:
        environment = await self._projects_api.get_environment_by_id(environment_id)
        if environment is None:
            raise ObservabilityEnvironmentNotFound()

        ready = None
        policy_id: str | None = None
        if source == AlertRuleSource.CLOUDFLARE_NATIVE:
            if self._cloudflare_api is None:
                raise CloudflareNotBoundForAlerting()
            if cf_alert_type is None:
                raise MissingCloudflareAlertType()
            ready = await self._cloudflare_api.get_ready_client_for_environment(environment_id)
            if ready is None:
                raise CloudflareNotBoundForAlerting()
            webhook_path = f"/api/v1/webhooks/cloudflare-alert/{ready.cloudflare_account_id}"
            webhook_url = f"{root_settings.BACKEND_BASE_URL}{webhook_path}"
            webhook_destination_id = await self._cloudflare_api.ensure_webhook_destination(
                ready.cloudflare_account_id, webhook_url=webhook_url
            )
            policy_id = await ready.client.create_policy(
                cf_account_id=ready.cf_account_id,
                api_token=ready.api_token,
                name=name,
                alert_type=cf_alert_type,
                webhook_destination_id=webhook_destination_id,
            )

        rule = await self._uow.alert_rules.create(
            environment_id=environment_id,
            name=name,
            source=source,
            cf_alert_type=cf_alert_type,
            condition=condition,
            severity=severity,
        )

        if policy_id is not None:
            await self._uow.alert_rules.set_cf_policy_id(rule.id, cf_policy_id=policy_id)
            refetched = await self._uow.alert_rules.get_by_id(rule.id)
            if refetched is None:
                raise AlertRuleNotFound()
            rule = refetched
        elif source == AlertRuleSource.LOKI_QUERY:
            condition = condition or {}
            await self._loki_client.upsert_rule_group(
                endpoint_url=condition.get("endpoint_url", ""),
                namespace="itsm",
                group_name=f"alert-rule-{rule.id}",
                rule_name=f"alert-rule-{rule.id}",
                expr=condition["query"],
                for_duration=condition.get("for", "5m"),
                labels={"app_alert_rule_id": str(rule.id)},
                auth_header=None,
            )

        if channel_ids:
            await self._uow.alert_rules.set_channels(rule.id, channel_ids)
            refetched = await self._uow.alert_rules.get_by_id(rule.id)
            if refetched is None:
                raise AlertRuleNotFound()
            rule = refetched

        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=AlertingAuditActions.ALERT_RULE_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Alert rule '{name}' created",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            environment_id=environment_id,
        )
        return rule
