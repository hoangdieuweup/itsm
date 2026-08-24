"""HTTP layer for the observability module. Thin: parses the request,
delegates to a use case, wraps the result in ApiResponse.

Gating reuses RbacResources.ENVIRONMENT (READ for viewing config/running
queries, UPDATE for config CRUD) — Decision #2: loki_configs is a plain
1:1-per-environment setting, no 2-layer ACL needed, zero new RBAC catalog
rows."""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.core.models import ApiResponse, ErrorPayload
from app.integrations.loki.schemas import LokiLogEntry
from app.modules.observability.dependencies import (
    get_create_loki_config,
    get_delete_loki_config,
    get_get_loki_config,
    get_run_log_query,
    get_stream_log_tail,
    get_update_loki_config,
)
from app.modules.observability.schemas import (
    LogQueryRequest,
    LogQueryResponse,
    LokiConfigCreate,
    LokiConfigRead,
    LokiConfigUpdate,
)
from app.modules.observability.services.create_loki_config import CreateLokiConfig
from app.modules.observability.services.delete_loki_config import DeleteLokiConfig
from app.modules.observability.services.get_loki_config import GetLokiConfig
from app.modules.observability.services.run_log_query import RunLogQuery
from app.modules.observability.services.stream_log_tail import StreamLogTail
from app.modules.observability.services.update_loki_config import UpdateLokiConfig
from app.modules.rbac.public import RbacActions, RbacResources, require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["observability"])


@router.post("/environments/{environment_id}/loki-config")
async def create_loki_config(
    environment_id: UUID,
    body: LokiConfigCreate,
    use_case: CreateLokiConfig = Depends(get_create_loki_config),
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.UPDATE)),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id, **body.model_dump(), actor=user)
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.get("/environments/{environment_id}/loki-config")
async def get_loki_config(
    environment_id: UUID,
    use_case: GetLokiConfig = Depends(get_get_loki_config),
    _user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.READ)),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id)
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.patch("/environments/{environment_id}/loki-config")
async def update_loki_config(
    environment_id: UUID,
    body: LokiConfigUpdate,
    use_case: UpdateLokiConfig = Depends(get_update_loki_config),
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.UPDATE)),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id, **body.model_dump(exclude_unset=True), actor=user)
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.delete("/environments/{environment_id}/loki-config")
async def delete_loki_config(
    environment_id: UUID,
    use_case: DeleteLokiConfig = Depends(get_delete_loki_config),
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.UPDATE)),
) -> ApiResponse[None]:
    await use_case.execute(environment_id, actor=user)
    return ApiResponse[None](success=True, data=None)


@router.post("/environments/{environment_id}/loki-config/query")
async def run_log_query(
    environment_id: UUID,
    body: LogQueryRequest,
    use_case: RunLogQuery = Depends(get_run_log_query),
    _user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.READ)),
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
    _user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.READ)),
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
                yield {"event": "message", "data": payload.model_dump_json(by_alias=True)}
        except Exception as exc:  # noqa: BLE001 -- mid-stream errors must become a final SSE event, not propagate
            error = ErrorPayload(code=getattr(exc, "code", "loki_unavailable"), message=str(exc))
            payload_err: ApiResponse[None] = ApiResponse(success=False, error=error)
            yield {"event": "message", "data": payload_err.model_dump_json(by_alias=True)}

    return EventSourceResponse(event_stream(), headers={"X-Accel-Buffering": "no"})

