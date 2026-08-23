"""HTTP entry points of the audit module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.audit.constants import AuditEventType
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.audit.schemas import AuditLogEntry
from app.modules.rbac.public import RbacActions, RbacResources, require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["audit"])


@router.get("/audit-logs")
async def list_audit_logs(
    project_id: UUID | None = Query(None),
    environment_id: UUID | None = Query(None),
    type: AuditEventType | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    pagination: PaginationParams = Depends(pagination_params),
    audit_api: AuditApi = Depends(get_audit_api),
    _user: UserRead = Depends(require_permission(RbacResources.AUDIT_LOG, RbacActions.READ)),
) -> ApiResponse[Page[AuditLogEntry]]:
    """List audit log entries, newest first, optionally filtered."""
    items, total = await audit_api.list_logs(
        project_id=project_id,
        environment_id=environment_id,
        type=type,
        since=since,
        until=until,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    page = Page[AuditLogEntry](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[AuditLogEntry]](success=True, data=page)
