"""HTTP layer for the observability module. Thin: parses the request,
delegates to a use case, wraps the result in ApiResponse.

Gating reuses RbacResources.ENVIRONMENT (READ for viewing config/running
queries, UPDATE for config CRUD) — Decision #2: loki_configs is a plain
1:1-per-environment setting, no 2-layer ACL needed, zero new RBAC catalog
rows."""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse

from app.core.models import ApiResponse, ErrorPayload
from app.integrations.loki.schemas import LokiLogEntry
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.public import require_account_access
from app.modules.observability.constants import IncidentStatus, ObservabilityDefaults
from app.modules.observability.dependencies import (
    get_acknowledge_incident,
    get_create_alert_rule,
    get_create_loki_config,
    get_create_manual_incident,
    get_delete_alert_rule,
    get_delete_loki_config,
    get_get_incident,
    get_get_loki_config,
    get_handle_cloudflare_webhook,
    get_handle_loki_webhook,
    get_list_alert_rules,
    get_list_available_alerts,
    get_list_incidents,
    get_resolve_incident,
    get_run_log_query,
    get_stream_log_tail,
    get_update_alert_rule,
    get_update_loki_config,
    require_project_permission_for_alert_rule,
    require_project_permission_for_environment,
    require_project_permission_for_incident,
    verify_cloudflare_webhook_secret,
    verify_loki_webhook_secret,
)
from app.modules.observability.schemas import (
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleUpdate,
    AvailableAlertOption,
    CreateManualIncidentRequest,
    IncidentRead,
    LogQueryRequest,
    LogQueryResponse,
    LokiConfigCreate,
    LokiConfigRead,
    LokiConfigUpdate,
)
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
from app.modules.rbac.public import RbacActions, RbacResources, require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["observability"])


@router.post("/environments/{environment_id}/loki-config")
async def create_loki_config(
    environment_id: UUID,
    body: LokiConfigCreate,
    use_case: CreateLokiConfig = Depends(get_create_loki_config),
    user: UserRead = Depends(
        require_project_permission_for_environment(RbacResources.PROJECT_LOKI_CONFIG, RbacActions.MANAGE)
    ),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id, **body.model_dump(), actor=user)
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.get("/environments/{environment_id}/loki-config")
async def get_loki_config(
    environment_id: UUID,
    use_case: GetLokiConfig = Depends(get_get_loki_config),
    _user: UserRead = Depends(
        require_project_permission_for_environment(RbacResources.PROJECT_LOKI_CONFIG, RbacActions.READ)
    ),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id)
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.patch("/environments/{environment_id}/loki-config")
async def update_loki_config(
    environment_id: UUID,
    body: LokiConfigUpdate,
    use_case: UpdateLokiConfig = Depends(get_update_loki_config),
    user: UserRead = Depends(
        require_project_permission_for_environment(RbacResources.PROJECT_LOKI_CONFIG, RbacActions.MANAGE)
    ),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id, **body.model_dump(exclude_unset=True), actor=user)
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.delete("/environments/{environment_id}/loki-config")
async def delete_loki_config(
    environment_id: UUID,
    use_case: DeleteLokiConfig = Depends(get_delete_loki_config),
    user: UserRead = Depends(
        require_project_permission_for_environment(RbacResources.PROJECT_LOKI_CONFIG, RbacActions.MANAGE)
    ),
) -> ApiResponse[None]:
    await use_case.execute(environment_id, actor=user)
    return ApiResponse[None](success=True, data=None)


@router.post("/environments/{environment_id}/loki-config/query")
async def run_log_query(
    environment_id: UUID,
    body: LogQueryRequest,
    use_case: RunLogQuery = Depends(get_run_log_query),
    _user: UserRead = Depends(
        require_project_permission_for_environment(RbacResources.PROJECT_LOKI_CONFIG, RbacActions.READ)
    ),
) -> ApiResponse[LogQueryResponse]:
    """POST, not GET — a LogQL query string can be long/awkward in a query
    string, and this is semantically an action ('run this query'), not a
    cacheable resource fetch."""
    result = await use_case.execute(environment_id=environment_id, **body.model_dump())
    return ApiResponse[LogQueryResponse](success=True, data=LogQueryResponse(entries=result.entries))


@router.get("/environments/{environment_id}/loki-config/tail")
async def stream_log_tail(
    environment_id: UUID,
    query: str,
    limit: int = 100,
    config_check: GetLokiConfig = Depends(get_get_loki_config),
    use_case: StreamLogTail = Depends(get_stream_log_tail),
    _user: UserRead = Depends(
        require_project_permission_for_environment(RbacResources.PROJECT_LOKI_CONFIG, RbacActions.READ)
    ),
) -> EventSourceResponse:
    """SSE bridge to Loki's WebSocket /tail. `config_check` runs a
    pre-flight GetLokiConfig call BEFORE the SSE response is constructed —
    EventSourceResponse commits the response (status 200 + headers) as soon
    as it's returned, pulling the first item from the body iterator eagerly
    rather than lazily (verified directly against the installed
    sse_starlette==3.4.8), so a LokiConfigNotFound raised from inside the
    generator itself would surface as a broken response instead of a normal
    404. Any error AFTER streaming has genuinely started (a dropped Loki
    connection, etc.) is still turned into one final success:false event
    per api-contract.md, never a silent close."""
    await config_check.execute(environment_id)

    async def event_stream() -> AsyncIterator[dict]:
        try:
            async for entry in use_case.execute(environment_id=environment_id, query=query, limit=limit):
                payload: ApiResponse[LokiLogEntry] = ApiResponse(success=True, data=entry)
                yield {
                    "event": ObservabilityDefaults.SSE_EVENT_MESSAGE,
                    "data": payload.model_dump_json(by_alias=True),
                }
        except Exception as exc:  # noqa: BLE001 -- mid-stream errors must become a final SSE event, not propagate
            error = ErrorPayload(
                code=getattr(exc, "code", ObservabilityDefaults.ERROR_LOKI_UNAVAILABLE), message=str(exc)
            )
            payload_err: ApiResponse[None] = ApiResponse(success=False, error=error)
            yield {
                "event": ObservabilityDefaults.SSE_EVENT_MESSAGE,
                "data": payload_err.model_dump_json(by_alias=True),
            }

    return EventSourceResponse(
        event_stream(), headers={"X-Accel-Buffering": ObservabilityDefaults.SSE_HEADER_NO_BUFFERING}
    )


@router.get("/cloudflare-accounts/{account_id}/available-alerts")
async def list_available_alerts(
    account_id: UUID,
    use_case: ListAvailableAlerts = Depends(get_list_available_alerts),
    _grant=Depends(require_account_access(AccessLevel.VIEWER)),
) -> ApiResponse[list[AvailableAlertOption]]:
    return ApiResponse[list[AvailableAlertOption]](success=True, data=await use_case.execute(account_id))


@router.post("/environments/{environment_id}/alert-rules")
async def create_alert_rule(
    environment_id: UUID,
    body: AlertRuleCreate,
    use_case: CreateAlertRule = Depends(get_create_alert_rule),
    user: UserRead = Depends(
        require_project_permission_for_environment(RbacResources.PROJECT_ALERT_RULE, RbacActions.CREATE)
    ),
) -> ApiResponse[AlertRuleRead]:
    result = await use_case.execute(environment_id=environment_id, **body.model_dump(), actor=user)
    return ApiResponse[AlertRuleRead](success=True, data=result)


@router.get("/environments/{environment_id}/alert-rules")
async def list_alert_rules(
    environment_id: UUID,
    use_case: ListAlertRules = Depends(get_list_alert_rules),
    _user: UserRead = Depends(
        require_project_permission_for_environment(RbacResources.PROJECT_ALERT_RULE, RbacActions.READ)
    ),
) -> ApiResponse[list[AlertRuleRead]]:
    return ApiResponse[list[AlertRuleRead]](success=True, data=await use_case.execute(environment_id))


@router.patch("/alert-rules/{alert_rule_id}")
async def update_alert_rule(
    alert_rule_id: UUID,
    body: AlertRuleUpdate,
    use_case: UpdateAlertRule = Depends(get_update_alert_rule),
    user: UserRead = Depends(
        require_project_permission_for_alert_rule(RbacResources.PROJECT_ALERT_RULE, RbacActions.UPDATE)
    ),
) -> ApiResponse[AlertRuleRead]:
    result = await use_case.execute(alert_rule_id, **body.model_dump(exclude_unset=True), actor=user)
    return ApiResponse[AlertRuleRead](success=True, data=result)


@router.delete("/alert-rules/{alert_rule_id}")
async def delete_alert_rule(
    alert_rule_id: UUID,
    use_case: DeleteAlertRule = Depends(get_delete_alert_rule),
    user: UserRead = Depends(
        require_project_permission_for_alert_rule(RbacResources.PROJECT_ALERT_RULE, RbacActions.DELETE)
    ),
) -> ApiResponse[None]:
    await use_case.execute(alert_rule_id, actor=user)
    return ApiResponse[None](success=True, data=None)


@router.get("/incidents")
async def list_incidents(
    project_id: UUID | None = Query(default=None, alias="projectId"),
    environment_id: UUID | None = Query(default=None, alias="environmentId"),
    status: IncidentStatus | None = Query(default=None),
    use_case: ListIncidents = Depends(get_list_incidents),
    _user: UserRead = Depends(require_permission(RbacResources.INCIDENT, RbacActions.READ)),
) -> ApiResponse[list[IncidentRead]]:
    items, _total = await use_case.execute(
        project_id=project_id, environment_id=environment_id, status=status, limit=50, offset=0
    )
    return ApiResponse[list[IncidentRead]](success=True, data=items)


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: UUID,
    use_case: GetIncident = Depends(get_get_incident),
    _user: UserRead = Depends(
        require_project_permission_for_incident(RbacResources.PROJECT_INCIDENT, RbacActions.READ)
    ),
) -> ApiResponse[IncidentRead]:
    return ApiResponse[IncidentRead](success=True, data=await use_case.execute(incident_id))


@router.post("/incidents")
async def create_manual_incident(
    body: CreateManualIncidentRequest,
    use_case: CreateManualIncident = Depends(get_create_manual_incident),
    auth_api: AuthApi = Depends(get_auth_api),
) -> ApiResponse[IncidentRead]:
    """No Depends(require_permission(...)) here — environment_id is body-only
    and incident.create is itself project-role-assignable (Decision, Task 8),
    so a global-only Layer-1 gate would 403 a project-role holder before
    their grant is ever consulted. CreateManualIncident resolves the full
    project-permission check itself via ProjectsApi.resolve_effective_permissions."""
    user = auth_api.current_user()
    result = await use_case.execute(**body.model_dump(), actor=user)
    return ApiResponse[IncidentRead](success=True, data=result)


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(
    incident_id: UUID,
    use_case: AcknowledgeIncident = Depends(get_acknowledge_incident),
    user: UserRead = Depends(
        require_project_permission_for_incident(RbacResources.PROJECT_INCIDENT, RbacActions.ACKNOWLEDGE)
    ),
) -> ApiResponse[IncidentRead]:
    return ApiResponse[IncidentRead](success=True, data=await use_case.execute(incident_id, actor=user))


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: UUID,
    use_case: ResolveIncident = Depends(get_resolve_incident),
    user: UserRead = Depends(
        require_project_permission_for_incident(RbacResources.PROJECT_INCIDENT, RbacActions.RESOLVE)
    ),
) -> ApiResponse[IncidentRead]:
    return ApiResponse[IncidentRead](success=True, data=await use_case.execute(incident_id, actor=user))


@router.post("/webhooks/cloudflare-alert/{cloudflare_account_id}")
async def cloudflare_alert_webhook(
    cloudflare_account_id: UUID,
    payload: dict,
    use_case: HandleCloudflareWebhook = Depends(get_handle_cloudflare_webhook),
    _verified=Depends(verify_cloudflare_webhook_secret),
) -> ApiResponse[None]:
    await use_case.execute(cloudflare_account_id=cloudflare_account_id, payload=payload)
    return ApiResponse[None](success=True, data=None)


@router.post("/webhooks/loki-alert")
async def loki_alert_webhook(
    payload: dict,
    use_case: HandleLokiWebhook = Depends(get_handle_loki_webhook),
    _verified=Depends(verify_loki_webhook_secret),
) -> ApiResponse[None]:
    await use_case.execute(payload=payload)
    return ApiResponse[None](success=True, data=None)
