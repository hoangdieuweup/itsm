"""Create an alert rule. CLOUDFLARE_NATIVE: resolve the environment's bound
Cloudflare account -> ensure a webhook destination exists for it -> create
the Notification Policy -> persist with the real cf_policy_id (Decision #9).
The policy is scoped to the environment's own bound zone (filters.zones)
whenever the chosen alert_type supports it — a Cloudflare account is often
shared by several environments/projects, and an unscoped policy would fire
for every zone on the account, not just this one. LOKI_QUERY: push the rule
into Loki's own Ruler so it actually gets evaluated (Decision #10) —
storing it in our DB alone would never cause Loki to fire anything. Nothing
persists locally until the external call that source needs has already
succeeded, mirroring the "call the external system first" convention every
prior Cloudflare-write use case follows."""

from uuid import UUID

from app.config import settings as root_settings
from app.core.base.markers import helper, use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.public import CloudflareApi
from app.modules.observability.constants import (
    AlertingAuditActions,
    AlertRuleSource,
    AlertSeverity,
    LokiWebhookPayloadKeys,
    ObservabilityDefaults,
)
from app.modules.observability.exceptions import (
    AlertRuleNotFound,
    CloudflareNotBoundForAlerting,
    MissingCloudflareAlertType,
    ObservabilityEnvironmentNotFound,
)
from app.modules.observability.rules import AlertingRules
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

        policy_id: str | None = None
        if source == AlertRuleSource.CLOUDFLARE_NATIVE:
            policy_id = await self._setup_cloudflare_policy(environment_id, name, cf_alert_type)

        rule = await self._uow.alert_rules.create(
            environment_id=environment_id,
            name=name,
            source=source,
            cf_alert_type=cf_alert_type,
            condition=condition,
            severity=severity,
        )

        rule = await self._attach_rule_integrations(rule, source, policy_id, condition, channel_ids)

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

    @helper
    async def _setup_cloudflare_policy(
        self, environment_id: UUID, name: str, cf_alert_type: str | None
    ) -> str:
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
        available = await ready.client.list_available_alerts(
            cf_account_id=ready.cf_account_id, api_token=ready.api_token
        )
        matching = next((item for item in available if item.get("type") == cf_alert_type), None)
        filter_options = matching.get("filter_options") if matching else None
        zone_id = ready.zone_id if AlertingRules.supports_zone_filter(filter_options) else None
        return await ready.client.create_policy(
            cf_account_id=ready.cf_account_id,
            api_token=ready.api_token,
            name=name,
            alert_type=cf_alert_type,
            webhook_destination_id=webhook_destination_id,
            zone_id=zone_id,
        )

    @helper
    async def _setup_loki_ruler(self, rule_id: UUID, condition: dict | None) -> None:
        cond = condition or {}
        group_name = f"{ObservabilityDefaults.RULE_GROUP_PREFIX}{rule_id}"
        await self._loki_client.upsert_rule_group(
            endpoint_url=cond.get(LokiWebhookPayloadKeys.ENDPOINT_URL, ""),
            namespace=ObservabilityDefaults.DEFAULT_LOKI_NAMESPACE,
            group_name=group_name,
            rule_name=group_name,
            expr=cond[LokiWebhookPayloadKeys.QUERY],
            for_duration=cond.get(
                LokiWebhookPayloadKeys.FOR, ObservabilityDefaults.DEFAULT_LOKI_FOR_DURATION
            ),
            labels={LokiWebhookPayloadKeys.APP_ALERT_RULE_ID: str(rule_id)},
            auth_header=None,
        )

    @helper
    async def _attach_rule_integrations(
        self,
        rule: AlertRuleRead,
        source: AlertRuleSource,
        policy_id: str | None,
        condition: dict | None,
        channel_ids: list[UUID],
    ) -> AlertRuleRead:
        if policy_id is not None:
            await self._uow.alert_rules.set_cf_policy_id(rule.id, cf_policy_id=policy_id)
            refetched = await self._uow.alert_rules.get_by_id(rule.id)
            if refetched is None:
                raise AlertRuleNotFound()
            rule = refetched
        elif source == AlertRuleSource.LOKI_QUERY:
            await self._setup_loki_ruler(rule.id, condition)

        if channel_ids:
            await self._uow.alert_rules.set_channels(rule.id, channel_ids)
            refetched = await self._uow.alert_rules.get_by_id(rule.id)
            if refetched is None:
                raise AlertRuleNotFound()
            rule = refetched

        return rule
