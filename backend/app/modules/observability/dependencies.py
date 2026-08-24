"""FastAPI dependency providers for the observability module. Every provider
depends on an Abstract* contract."""

import hmac
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.loki.client import LokiClient
from app.integrations.loki.dependencies import get_loki_client
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.cloudflare.public import CloudflareApi, get_cloudflare_api
from app.modules.notifications.public import NotificationsApi, get_notifications_api
from app.modules.observability.config import observability_settings
from app.modules.observability.exceptions import InvalidWebhookSecret
from app.modules.observability.services.acknowledge_incident import AcknowledgeIncident
from app.modules.observability.services.create_alert_rule import CreateAlertRule
from app.modules.observability.services.create_loki_config import CreateLokiConfig
from app.modules.observability.services.create_manual_incident import CreateManualIncident
from app.modules.observability.services.delete_alert_rule import DeleteAlertRule
from app.modules.observability.services.delete_loki_config import DeleteLokiConfig
from app.modules.observability.services.get_incident import GetIncident
from app.modules.observability.services.get_loki_config import GetLokiConfig
from app.modules.observability.services.handle_cloudflare_webhook import HandleCloudflareWebhook
from app.modules.observability.services.handle_loki_webhook import HandleLokiWebhook
from app.modules.observability.services.list_alert_rules import ListAlertRules
from app.modules.observability.services.list_available_alerts import ListAvailableAlerts
from app.modules.observability.services.list_incidents import ListIncidents
from app.modules.observability.services.resolve_incident import ResolveIncident
from app.modules.observability.services.run_log_query import RunLogQuery
from app.modules.observability.services.stream_log_tail import StreamLogTail
from app.modules.observability.services.update_alert_rule import UpdateAlertRule
from app.modules.observability.services.update_loki_config import UpdateLokiConfig
from app.modules.observability.uow import AbstractObservabilityUnitOfWork, ObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi, get_projects_api


async def get_uow(session: AsyncSession = Depends(get_session)) -> ObservabilityUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return ObservabilityUnitOfWork(session)


async def get_create_loki_config(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateLokiConfig:
    return CreateLokiConfig(uow, projects_api, audit_api)


async def get_get_loki_config(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
) -> GetLokiConfig:
    return GetLokiConfig(uow)


async def get_update_loki_config(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateLokiConfig:
    return UpdateLokiConfig(uow, audit_api)


async def get_delete_loki_config(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteLokiConfig:
    return DeleteLokiConfig(uow, audit_api)


async def get_run_log_query(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    client: LokiClient = Depends(get_loki_client),
) -> RunLogQuery:
    return RunLogQuery(uow, client)


async def get_stream_log_tail(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    client: LokiClient = Depends(get_loki_client),
) -> StreamLogTail:
    return StreamLogTail(uow, client)


async def verify_cloudflare_webhook_secret(
    cloudflare_account_id: UUID,
    cf_webhook_auth: str | None = Header(default=None),
    cloudflare_api: CloudflareApi = Depends(get_cloudflare_api),
) -> None:
    """Reject unless cf-webhook-auth matches the secret stored for this
    account (Decision #5 — the path segment is what resolves WHICH secret
    to check, never a body/payload field). Uses CloudflareApi.get_webhook_secret
    (Task 5) — the read-only counterpart of ensure_webhook_destination."""
    stored_secret = await cloudflare_api.get_webhook_secret(cloudflare_account_id)
    if not stored_secret or not cf_webhook_auth or not hmac.compare_digest(cf_webhook_auth, stored_secret):
        raise InvalidWebhookSecret()


async def get_list_available_alerts(
    cloudflare_api: CloudflareApi = Depends(get_cloudflare_api),
) -> ListAvailableAlerts:
    return ListAvailableAlerts(cloudflare_api)


async def get_create_alert_rule(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    cloudflare_api: CloudflareApi = Depends(get_cloudflare_api),
    loki_client: LokiClient = Depends(get_loki_client),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateAlertRule:
    return CreateAlertRule(
        uow,
        cloudflare_api=cloudflare_api,
        loki_client=loki_client,
        projects_api=projects_api,
        audit_api=audit_api,
    )


async def get_update_alert_rule(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateAlertRule:
    return UpdateAlertRule(uow, audit_api)


async def get_delete_alert_rule(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    cloudflare_api: CloudflareApi = Depends(get_cloudflare_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteAlertRule:
    return DeleteAlertRule(uow, cloudflare_api, audit_api)


async def get_list_alert_rules(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
) -> ListAlertRules:
    return ListAlertRules(uow)


async def get_handle_cloudflare_webhook(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    notifications_api: NotificationsApi = Depends(get_notifications_api),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> HandleCloudflareWebhook:
    return HandleCloudflareWebhook(
        uow, notifications_api=notifications_api, projects_api=projects_api, audit_api=audit_api
    )


async def get_handle_loki_webhook(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    notifications_api: NotificationsApi = Depends(get_notifications_api),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> HandleLokiWebhook:
    return HandleLokiWebhook(
        uow, notifications_api=notifications_api, projects_api=projects_api, audit_api=audit_api
    )


async def get_create_manual_incident(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateManualIncident:
    return CreateManualIncident(uow, projects_api=projects_api, audit_api=audit_api)


async def get_acknowledge_incident(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> AcknowledgeIncident:
    return AcknowledgeIncident(uow, audit_api=audit_api)


async def get_resolve_incident(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> ResolveIncident:
    return ResolveIncident(uow, audit_api=audit_api)


async def get_list_incidents(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
) -> ListIncidents:
    return ListIncidents(uow)


async def get_get_incident(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
) -> GetIncident:
    return GetIncident(uow)


async def verify_loki_webhook_secret(authorization: str | None = Header(default=None)) -> None:
    """Bearer-token check against one app-wide shared secret (Decision #11) —
    Alertmanager's http_config.authorization sends this natively."""
    expected = f"Bearer {observability_settings.LOKI_WEBHOOK_SECRET}"
    if (
        not authorization
        or not observability_settings.LOKI_WEBHOOK_SECRET
        or not hmac.compare_digest(authorization, expected)
    ):
        raise InvalidWebhookSecret()
