"""HTTP entry points of the projects module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.projects.access import resolve_project_permissions
from app.modules.projects.dependencies import (
    get_add_project_member,
    get_assign_member_project_role,
    get_create_environment,
    get_create_project,
    get_create_project_link,
    get_create_project_role,
    get_delete_environment,
    get_delete_project,
    get_delete_project_link,
    get_delete_project_role,
    get_list_assignable_permissions,
    get_list_project_members,
    get_list_project_roles,
    get_list_visible_projects,
    get_remove_project_member,
    get_uow,
    get_update_environment,
    get_update_project,
    get_update_project_link,
    get_update_project_role,
    require_project_membership,
    require_project_membership_for_project_role,
    require_project_permission,
    require_project_permission_for_environment,
    require_project_permission_for_link,
)
from app.modules.projects.exceptions import EnvironmentNotFound, ProjectNotFound
from app.modules.projects.schemas import (
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentUpdate,
    ProjectCreate,
    ProjectLinkCreate,
    ProjectLinkRead,
    ProjectLinkUpdate,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberRoleAssign,
    ProjectPermissionGrant,
    ProjectPermissionSetRead,
    ProjectRead,
    ProjectRoleCreate,
    ProjectRoleRead,
    ProjectRoleUpdate,
    ProjectUpdate,
)
from app.modules.projects.services.add_project_member import AddProjectMember
from app.modules.projects.services.assign_member_project_role import AssignMemberProjectRole
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.create_project_role import CreateProjectRole
from app.modules.projects.services.delete_environment import DeleteEnvironment
from app.modules.projects.services.delete_project import DeleteProject
from app.modules.projects.services.delete_project_link import DeleteProjectLink
from app.modules.projects.services.delete_project_role import DeleteProjectRole
from app.modules.projects.services.list_assignable_permissions import ListAssignablePermissions
from app.modules.projects.services.list_project_members import ListProjectMembers
from app.modules.projects.services.list_project_roles import ListProjectRoles
from app.modules.projects.services.list_visible_projects import ListVisibleProjects
from app.modules.projects.services.remove_project_member import RemoveProjectMember
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.services.update_project_role import UpdateProjectRole
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import (
    PermissionRead,
    RbacActions,
    RbacApi,
    RbacResources,
    get_rbac_api,
    require_permission,
)
from app.modules.users.public import UserRead

router = APIRouter(tags=["projects"])


@router.post("/projects")
async def create_project(
    body: ProjectCreate,
    use_case: CreateProject = Depends(get_create_project),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.CREATE)),
) -> ApiResponse[ProjectRead]:
    """Create a new project — auto-attaches the configured default Jira/Git
    links and adds the creator as its first member."""
    project = await use_case.execute(body.name, body.description, actor_id=user.id, actor_email=user.email)
    return ApiResponse[ProjectRead](success=True, data=project)


@router.get("/projects")
async def list_projects(
    pagination: PaginationParams = Depends(pagination_params),
    use_case: ListVisibleProjects = Depends(get_list_visible_projects),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.READ)),
) -> ApiResponse[Page[ProjectRead]]:
    """List projects visible to the current user — every project if they
    hold project:manage_all, otherwise only the ones they're a member of."""
    items, total = await use_case.execute(user.id, pagination.limit, pagination.offset)
    page = Page[ProjectRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[ProjectRead]](success=True, data=page)


@router.get("/projects/assignable-permissions")
async def list_assignable_permissions(
    use_case: ListAssignablePermissions = Depends(get_list_assignable_permissions),
    _user: UserRead = Depends(require_permission(RbacResources.PROJECT_ROLE, RbacActions.READ)),
) -> ApiResponse[list[PermissionRead]]:
    """List the permission catalog subset a project role may ever grant —
    backs the project-role editor's checkbox grid. Global (no project_id
    in path), gated by the global project_role:read atom alone."""
    permissions = await use_case.execute()
    return ApiResponse[list[PermissionRead]](success=True, data=permissions)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT, RbacActions.READ)
    ),
) -> ApiResponse[ProjectRead]:
    """Return one project, 404 if it doesn't exist."""
    project = await uow.projects.get_by_id(project_id)
    if project is None:
        raise ProjectNotFound()
    return ApiResponse[ProjectRead](success=True, data=project)


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    use_case: UpdateProject = Depends(get_update_project),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT, RbacActions.UPDATE)
    ),
) -> ApiResponse[ProjectRead]:
    """Rename and/or redescribe a project."""
    project = await use_case.execute(
        project_id,
        name=body.name,
        description=body.description,
        actor_id=grant.user.id,
        actor_email=grant.user.email,
    )
    return ApiResponse[ProjectRead](success=True, data=project)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: UUID,
    use_case: DeleteProject = Depends(get_delete_project),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT, RbacActions.DELETE)
    ),
) -> ApiResponse[None]:
    """Delete a project. Its environments and links cascade at the DB level."""
    await use_case.execute(project_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/environments")
async def list_environments(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.ENVIRONMENT, RbacActions.READ)
    ),
) -> ApiResponse[list[EnvironmentRead]]:
    """List a project's environments."""
    environments = await uow.environments.list_for_project(project_id)
    return ApiResponse[list[EnvironmentRead]](success=True, data=environments)


@router.post("/projects/{project_id}/environments")
async def create_environment(
    project_id: UUID,
    body: EnvironmentCreate,
    use_case: CreateEnvironment = Depends(get_create_environment),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.ENVIRONMENT, RbacActions.CREATE)
    ),
) -> ApiResponse[EnvironmentRead]:
    """Create an environment. Rejected if the project already has one of this type."""
    env = await use_case.execute(
        project_id, body.type, body.name, body.base_url, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[EnvironmentRead](success=True, data=env)


@router.get("/environments/{environment_id}")
async def get_environment(
    environment_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission_for_environment(RbacResources.ENVIRONMENT, RbacActions.READ)
    ),
) -> ApiResponse[EnvironmentRead]:
    """Return one environment, 404 if it doesn't exist."""
    environment = await uow.environments.get_by_id(environment_id)
    if environment is None:
        raise EnvironmentNotFound()
    return ApiResponse[EnvironmentRead](success=True, data=environment)


@router.patch("/environments/{environment_id}")
async def update_environment(
    environment_id: UUID,
    body: EnvironmentUpdate,
    use_case: UpdateEnvironment = Depends(get_update_environment),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission_for_environment(RbacResources.ENVIRONMENT, RbacActions.UPDATE)
    ),
) -> ApiResponse[EnvironmentRead]:
    """Rename and/or re-point an environment."""
    env = await use_case.execute(
        environment_id,
        name=body.name,
        base_url=body.base_url,
        actor_id=grant.user.id,
        actor_email=grant.user.email,
    )
    return ApiResponse[EnvironmentRead](success=True, data=env)


@router.delete("/environments/{environment_id}")
async def delete_environment(
    environment_id: UUID,
    use_case: DeleteEnvironment = Depends(get_delete_environment),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission_for_environment(RbacResources.ENVIRONMENT, RbacActions.DELETE)
    ),
) -> ApiResponse[None]:
    """Delete an environment."""
    await use_case.execute(environment_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/links")
async def list_project_links(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_LINK, RbacActions.READ)
    ),
) -> ApiResponse[list[ProjectLinkRead]]:
    """List a project's external links."""
    links = await uow.project_links.list_for_project(project_id)
    return ApiResponse[list[ProjectLinkRead]](success=True, data=links)


@router.post("/projects/{project_id}/links")
async def create_project_link(
    project_id: UUID,
    body: ProjectLinkCreate,
    use_case: CreateProjectLink = Depends(get_create_project_link),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_LINK, RbacActions.MANAGE)
    ),
) -> ApiResponse[ProjectLinkRead]:
    """Add an external link to a project."""
    link = await use_case.execute(project_id, body.type, body.name, body.url)
    return ApiResponse[ProjectLinkRead](success=True, data=link)


@router.patch("/links/{link_id}")
async def update_project_link(
    link_id: UUID,
    body: ProjectLinkUpdate,
    use_case: UpdateProjectLink = Depends(get_update_project_link),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission_for_link(RbacResources.PROJECT_LINK, RbacActions.MANAGE)
    ),
) -> ApiResponse[ProjectLinkRead]:
    """Rename and/or re-point a project link."""
    link = await use_case.execute(link_id, name=body.name, url=body.url)
    return ApiResponse[ProjectLinkRead](success=True, data=link)


@router.delete("/links/{link_id}")
async def delete_project_link(
    link_id: UUID,
    use_case: DeleteProjectLink = Depends(get_delete_project_link),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission_for_link(RbacResources.PROJECT_LINK, RbacActions.MANAGE)
    ),
) -> ApiResponse[None]:
    """Remove a project link."""
    await use_case.execute(link_id)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/members")
async def list_project_members(
    project_id: UUID,
    use_case: ListProjectMembers = Depends(get_list_project_members),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_MEMBER, RbacActions.READ)
    ),
) -> ApiResponse[list[ProjectMemberRead]]:
    """List a project's members."""
    members = await use_case.execute(project_id)
    return ApiResponse[list[ProjectMemberRead]](success=True, data=members)


@router.post("/projects/{project_id}/members")
async def add_project_member(
    project_id: UUID,
    body: ProjectMemberCreate,
    use_case: AddProjectMember = Depends(get_add_project_member),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_MEMBER, RbacActions.MANAGE)
    ),
) -> ApiResponse[None]:
    """Add a user as a member of a project."""
    await use_case.execute(project_id, body.user_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.delete("/projects/{project_id}/members/{user_id}")
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    use_case: RemoveProjectMember = Depends(get_remove_project_member),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_MEMBER, RbacActions.MANAGE)
    ),
) -> ApiResponse[None]:
    """Remove a user's membership on a project."""
    await use_case.execute(project_id, user_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/roles")
async def list_project_roles(
    project_id: UUID,
    use_case: ListProjectRoles = Depends(get_list_project_roles),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_ROLE, RbacActions.READ)
    ),
) -> ApiResponse[list[ProjectRoleRead]]:
    """List a project's roles."""
    roles = await use_case.execute(project_id)
    return ApiResponse[list[ProjectRoleRead]](success=True, data=roles)


@router.post("/projects/{project_id}/roles")
async def create_project_role(
    project_id: UUID,
    body: ProjectRoleCreate,
    use_case: CreateProjectRole = Depends(get_create_project_role),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_ROLE, RbacActions.MANAGE)
    ),
) -> ApiResponse[ProjectRoleRead]:
    """Create a project-scoped role."""
    role = await use_case.execute(
        project_id, body.name, body.permission_ids, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[ProjectRoleRead](success=True, data=role)


@router.patch("/project-roles/{project_role_id}")
async def update_project_role(
    project_role_id: UUID,
    body: ProjectRoleUpdate,
    use_case: UpdateProjectRole = Depends(get_update_project_role),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT_ROLE, RbacActions.MANAGE)),
    _membership: None = Depends(require_project_membership_for_project_role()),
) -> ApiResponse[ProjectRoleRead]:
    """Rename and/or re-permission a project role."""
    role = await use_case.execute(
        project_role_id,
        name=body.name,
        permission_ids=body.permission_ids,
        actor_id=user.id,
        actor_email=user.email,
    )
    return ApiResponse[ProjectRoleRead](success=True, data=role)


@router.delete("/project-roles/{project_role_id}")
async def delete_project_role(
    project_role_id: UUID,
    use_case: DeleteProjectRole = Depends(get_delete_project_role),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT_ROLE, RbacActions.MANAGE)),
    _membership: None = Depends(require_project_membership_for_project_role()),
) -> ApiResponse[None]:
    """Delete a project role. Members holding it degrade to global-only (ON DELETE SET NULL)."""
    await use_case.execute(project_role_id, actor_id=user.id, actor_email=user.email)
    return ApiResponse[None](success=True)


@router.put("/projects/{project_id}/members/{user_id}/role")
async def assign_member_project_role(
    project_id: UUID,
    user_id: UUID,
    body: ProjectMemberRoleAssign,
    use_case: AssignMemberProjectRole = Depends(get_assign_member_project_role),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_MEMBER, RbacActions.MANAGE)
    ),
) -> ApiResponse[None]:
    """Assign (or clear, body.projectRoleId=null) a member's project role."""
    await use_case.execute(
        project_id, user_id, body.project_role_id, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/permissions")
async def get_my_project_permissions(
    project_id: UUID,
    auth_api: AuthApi = Depends(get_auth_api),
    rbac_api: RbacApi = Depends(get_rbac_api),
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[ProjectPermissionSetRead]:
    """Self-read of the caller's own effective permission set in this
    project — gated by plain membership only (not require_project_
    permission — there's no single resource.action to check here, this
    IS the permission-set read)."""
    user = auth_api.current_user()
    grant = await resolve_project_permissions(project_id, user, rbac_api, uow)
    return ApiResponse[ProjectPermissionSetRead](
        success=True,
        data=ProjectPermissionSetRead(project_id=project_id, permissions=sorted(grant.permissions)),
    )
