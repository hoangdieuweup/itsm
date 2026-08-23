"""HTTP entry points of the rbac module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.rbac.constants import RbacActions, RbacResources
from app.modules.rbac.dependencies import get_create_role, get_delete_role, get_update_role
from app.modules.rbac.dependencies import get_uow as get_rbac_uow
from app.modules.rbac.exceptions import RoleNotFound
from app.modules.rbac.public import (
    get_assign_role,
    get_assign_roles,
    require_any_permission,
    require_permission,
)
from app.modules.rbac.schemas import (
    PermissionRead,
    RoleAssignment,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    UserRolesAssignment,
)
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.services.assign_roles import AssignRoles
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork
from app.modules.users.public import UserRead

router = APIRouter(prefix="/rbac", tags=["rbac"])


@router.post("/roles")
async def create_role(
    body: RoleCreate,
    use_case: CreateRole = Depends(get_create_role),
    _user: UserRead = Depends(require_permission(RbacResources.ROLE, RbacActions.CREATE)),
) -> ApiResponse[RoleRead]:
    """Create a new custom role."""
    role = await use_case.execute(body.name, body.permission_ids)
    return ApiResponse[RoleRead](success=True, data=role)


@router.get("/roles")
async def list_roles(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(
        require_any_permission(
            (RbacResources.ROLE, RbacActions.READ), (RbacResources.USER, RbacActions.ASSIGN_ROLE)
        )
    ),
) -> ApiResponse[Page[RoleRead]]:
    """List roles with their permissions."""
    items, total = await uow.roles.list_page(pagination.limit, pagination.offset)
    page = Page[RoleRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[RoleRead]](success=True, data=page)


@router.get("/roles/{role_id}")
async def get_role(
    role_id: UUID,
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission(RbacResources.ROLE, RbacActions.READ)),
) -> ApiResponse[RoleRead]:
    """Return one role, 404 if it doesn't exist."""
    role = await uow.roles.get_by_id(role_id)
    if role is None:
        raise RoleNotFound()
    return ApiResponse[RoleRead](success=True, data=role)


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: UUID,
    body: RoleUpdate,
    use_case: UpdateRole = Depends(get_update_role),
    _user: UserRead = Depends(require_permission(RbacResources.ROLE, RbacActions.UPDATE)),
) -> ApiResponse[RoleRead]:
    """Rename a role and/or replace its permission set."""
    role = await use_case.execute(role_id, name=body.name, permission_ids=body.permission_ids)
    return ApiResponse[RoleRead](success=True, data=role)


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: UUID,
    use_case: DeleteRole = Depends(get_delete_role),
    _user: UserRead = Depends(require_permission(RbacResources.ROLE, RbacActions.DELETE)),
) -> ApiResponse[None]:
    """Delete a custom role."""
    await use_case.execute(role_id)
    return ApiResponse[None](success=True)


@router.get("/permissions")
async def list_permissions(
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission(RbacResources.PERMISSION, RbacActions.READ)),
) -> ApiResponse[list[PermissionRead]]:
    """Return the fixed permission catalog, for building the role-edit checkbox UI."""
    permissions = await uow.permissions.list_all()
    return ApiResponse[list[PermissionRead]](success=True, data=permissions)


@router.put("/users/{user_id}/roles")
async def assign_user_roles(
    user_id: UUID,
    body: UserRolesAssignment,
    use_case: AssignRoles = Depends(get_assign_roles),
    _user: UserRead = Depends(require_permission(RbacResources.USER, RbacActions.ASSIGN_ROLE)),
) -> ApiResponse[None]:
    """Assign multiple roles to an existing user."""
    await use_case.execute(user_id, body.role_ids)
    return ApiResponse[None](success=True)


@router.get("/users/{user_id}/roles")
async def get_user_roles(
    user_id: UUID,
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission(RbacResources.USER, RbacActions.READ)),
) -> ApiResponse[list[RoleRead]]:
    """Return all roles assigned to a user."""
    roles = await uow.user_roles.get_roles_for_user(user_id)
    return ApiResponse[list[RoleRead]](success=True, data=roles)


@router.patch("/users/{user_id}/role")
async def assign_user_role(
    user_id: UUID,
    body: RoleAssignment,
    use_case: AssignRole = Depends(get_assign_role),
    _user: UserRead = Depends(require_permission(RbacResources.USER, RbacActions.ASSIGN_ROLE)),
) -> ApiResponse[None]:
    """Assign a single role to an existing user (backwards compatible)."""
    if body.role_id is not None:
        await use_case.execute(user_id, body.role_id)
    elif body.role_ids:
        await use_case.execute(user_id, body.role_ids[0])
    return ApiResponse[None](success=True)
