"""HTTP entry points of the rbac module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here."""

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.auth.schemas import UserRead
from app.modules.rbac.dependencies import get_create_role, get_delete_role, get_update_role
from app.modules.rbac.dependencies import get_uow as get_rbac_uow
from app.modules.rbac.exceptions import RoleNotFound
from app.modules.rbac.guards import get_assign_role, require_permission
from app.modules.rbac.schemas import PermissionRead, RoleAssignment, RoleCreate, RoleRead, RoleUpdate
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork

router = APIRouter(prefix="/rbac", tags=["rbac"])


@router.post("/roles")
async def create_role(
    body: RoleCreate,
    use_case: CreateRole = Depends(get_create_role),
    _user: UserRead = Depends(require_permission("role", "create")),
) -> ApiResponse[RoleRead]:
    """Create a new custom role."""
    role = await use_case.execute(body.name, body.permission_ids)
    return ApiResponse[RoleRead](success=True, data=role)


@router.get("/roles")
async def list_roles(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission("role", "read")),
) -> ApiResponse[Page[RoleRead]]:
    """List roles with their permissions."""
    items, total = await uow.roles.list_page(pagination.limit, pagination.offset)
    page = Page[RoleRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[RoleRead]](success=True, data=page)


@router.get("/roles/{role_id}")
async def get_role(
    role_id: int,
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission("role", "read")),
) -> ApiResponse[RoleRead]:
    """Return one role, 404 if it doesn't exist."""
    role = await uow.roles.get_by_id(role_id)
    if role is None:
        raise RoleNotFound()
    return ApiResponse[RoleRead](success=True, data=role)


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: int,
    body: RoleUpdate,
    use_case: UpdateRole = Depends(get_update_role),
    _user: UserRead = Depends(require_permission("role", "update")),
) -> ApiResponse[RoleRead]:
    """Rename a role and/or replace its permission set."""
    role = await use_case.execute(role_id, name=body.name, permission_ids=body.permission_ids)
    return ApiResponse[RoleRead](success=True, data=role)


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    use_case: DeleteRole = Depends(get_delete_role),
    _user: UserRead = Depends(require_permission("role", "delete")),
) -> ApiResponse[None]:
    """Delete a custom role."""
    await use_case.execute(role_id)
    return ApiResponse[None](success=True)


@router.get("/permissions")
async def list_permissions(
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission("permission", "read")),
) -> ApiResponse[list[PermissionRead]]:
    """Return the fixed permission catalog, for building the role-edit checkbox UI."""
    permissions = await uow.permissions.list_all()
    return ApiResponse[list[PermissionRead]](success=True, data=permissions)


@router.patch("/users/{user_id}/role")
async def assign_user_role(
    user_id: int,
    body: RoleAssignment,
    use_case: AssignRole = Depends(get_assign_role),
    _user: UserRead = Depends(require_permission("user", "assign_role")),
) -> ApiResponse[None]:
    """Assign a role to an existing user."""
    await use_case.execute(user_id, body.role_id)
    return ApiResponse[None](success=True)
