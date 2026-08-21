"""HTTP entry points of the users module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result
in ApiResponse — no formatting/business logic lives here.
"""

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.rbac.public import require_permission
from app.modules.users.dependencies import get_uow
from app.modules.users.schemas import UserRead, UserStatusUpdate
from app.modules.users.services.update_user_status import UpdateUserStatus
from app.modules.users.uow import AbstractUsersUnitOfWork
from app.modules.users.utils import get_update_user_status

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractUsersUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("user", "read")),
) -> ApiResponse[Page[UserRead]]:
    """List users for the admin user-management page."""
    items, total = await uow.users.list_page(pagination.limit, pagination.offset)
    page = Page[UserRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[UserRead]](success=True, data=page)


@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: int,
    body: UserStatusUpdate,
    use_case: UpdateUserStatus = Depends(get_update_user_status),
    _user: UserRead = Depends(require_permission("user", "update_status")),
) -> ApiResponse[UserRead]:
    """Block or unblock a user. Blocking the last admin is rejected — see rbac's bus-factor rule."""
    updated = await use_case.execute(user_id, body.status)
    return ApiResponse[UserRead](success=True, data=updated)
