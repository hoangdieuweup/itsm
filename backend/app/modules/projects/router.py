"""HTTP entry points of the projects module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.projects.dependencies import (
    get_add_project_member,
    get_create_environment,
    get_create_project,
    get_create_project_link,
    get_delete_environment,
    get_delete_project,
    get_delete_project_link,
    get_list_project_members,
    get_list_visible_projects,
    get_remove_project_member,
    get_uow,
    get_update_environment,
    get_update_project,
    get_update_project_link,
    require_project_membership,
    require_project_membership_for_environment,
    require_project_membership_for_link,
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
    ProjectRead,
    ProjectUpdate,
)
from app.modules.projects.services.add_project_member import AddProjectMember
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.delete_environment import DeleteEnvironment
from app.modules.projects.services.delete_project import DeleteProject
from app.modules.projects.services.delete_project_link import DeleteProjectLink
from app.modules.projects.services.list_project_members import ListProjectMembers
from app.modules.projects.services.list_visible_projects import ListVisibleProjects
from app.modules.projects.services.remove_project_member import RemoveProjectMember
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacActions, RbacResources, require_permission
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


@router.get("/projects/{project_id}")
async def get_project(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.READ)),
    _membership: None = Depends(require_project_membership()),
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
    user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.UPDATE)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[ProjectRead]:
    """Rename and/or redescribe a project."""
    project = await use_case.execute(
        project_id, name=body.name, description=body.description, actor_id=user.id, actor_email=user.email
    )
    return ApiResponse[ProjectRead](success=True, data=project)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: UUID,
    use_case: DeleteProject = Depends(get_delete_project),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.DELETE)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[None]:
    """Delete a project. Its environments and links cascade at the DB level."""
    await use_case.execute(project_id, actor_id=user.id, actor_email=user.email)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/environments")
async def list_environments(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.READ)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[list[EnvironmentRead]]:
    """List a project's environments."""
    environments = await uow.environments.list_for_project(project_id)
    return ApiResponse[list[EnvironmentRead]](success=True, data=environments)


@router.post("/projects/{project_id}/environments")
async def create_environment(
    project_id: UUID,
    body: EnvironmentCreate,
    use_case: CreateEnvironment = Depends(get_create_environment),
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.CREATE)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[EnvironmentRead]:
    """Create an environment. Rejected if the project already has one of this type."""
    env = await use_case.execute(
        project_id, body.type, body.name, body.base_url, actor_id=user.id, actor_email=user.email
    )
    return ApiResponse[EnvironmentRead](success=True, data=env)


@router.get("/environments/{environment_id}")
async def get_environment(
    environment_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.READ)),
    _membership: None = Depends(require_project_membership_for_environment()),
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
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.UPDATE)),
    _membership: None = Depends(require_project_membership_for_environment()),
) -> ApiResponse[EnvironmentRead]:
    """Rename and/or re-point an environment."""
    env = await use_case.execute(
        environment_id, name=body.name, base_url=body.base_url, actor_id=user.id, actor_email=user.email
    )
    return ApiResponse[EnvironmentRead](success=True, data=env)


@router.delete("/environments/{environment_id}")
async def delete_environment(
    environment_id: UUID,
    use_case: DeleteEnvironment = Depends(get_delete_environment),
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.DELETE)),
    _membership: None = Depends(require_project_membership_for_environment()),
) -> ApiResponse[None]:
    """Delete an environment."""
    await use_case.execute(environment_id, actor_id=user.id, actor_email=user.email)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/links")
async def list_project_links(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.READ)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[list[ProjectLinkRead]]:
    """List a project's external links."""
    links = await uow.project_links.list_for_project(project_id)
    return ApiResponse[list[ProjectLinkRead]](success=True, data=links)


@router.post("/projects/{project_id}/links")
async def create_project_link(
    project_id: UUID,
    body: ProjectLinkCreate,
    use_case: CreateProjectLink = Depends(get_create_project_link),
    _user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.UPDATE)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[ProjectLinkRead]:
    """Add an external link to a project."""
    link = await use_case.execute(project_id, body.type, body.name, body.url)
    return ApiResponse[ProjectLinkRead](success=True, data=link)


@router.patch("/links/{link_id}")
async def update_project_link(
    link_id: UUID,
    body: ProjectLinkUpdate,
    use_case: UpdateProjectLink = Depends(get_update_project_link),
    _user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.UPDATE)),
    _membership: None = Depends(require_project_membership_for_link()),
) -> ApiResponse[ProjectLinkRead]:
    """Rename and/or re-point a project link."""
    link = await use_case.execute(link_id, name=body.name, url=body.url)
    return ApiResponse[ProjectLinkRead](success=True, data=link)


@router.delete("/links/{link_id}")
async def delete_project_link(
    link_id: UUID,
    use_case: DeleteProjectLink = Depends(get_delete_project_link),
    _user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.UPDATE)),
    _membership: None = Depends(require_project_membership_for_link()),
) -> ApiResponse[None]:
    """Remove a project link."""
    await use_case.execute(link_id)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/members")
async def list_project_members(
    project_id: UUID,
    use_case: ListProjectMembers = Depends(get_list_project_members),
    _user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.READ)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[list[ProjectMemberRead]]:
    """List a project's members."""
    members = await use_case.execute(project_id)
    return ApiResponse[list[ProjectMemberRead]](success=True, data=members)


@router.post("/projects/{project_id}/members")
async def add_project_member(
    project_id: UUID,
    body: ProjectMemberCreate,
    use_case: AddProjectMember = Depends(get_add_project_member),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.UPDATE)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[None]:
    """Add a user as a member of a project."""
    await use_case.execute(project_id, body.user_id, actor_id=user.id, actor_email=user.email)
    return ApiResponse[None](success=True)


@router.delete("/projects/{project_id}/members/{user_id}")
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    use_case: RemoveProjectMember = Depends(get_remove_project_member),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT, RbacActions.UPDATE)),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[None]:
    """Remove a user's membership on a project."""
    await use_case.execute(project_id, user_id, actor_id=user.id, actor_email=user.email)
    return ApiResponse[None](success=True)
