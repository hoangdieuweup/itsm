"""HTTP layer for the observability module. Thin: parses the request,
delegates to a use case, wraps the result in ApiResponse.

Gating reuses RbacResources.ENVIRONMENT (READ for viewing config/running
queries, UPDATE for config CRUD) — Decision #2: loki_configs is a plain
1:1-per-environment setting, no 2-layer ACL needed, zero new RBAC catalog
rows."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.modules.observability.dependencies import (
    get_create_loki_config,
    get_delete_loki_config,
    get_get_loki_config,
    get_run_log_query,
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
