"""HTTP entry points of the projects module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.projects.dependencies import (
    get_create_environment,
    get_create_project,
    get_create_project_link,
    get_delete_environment,
    get_delete_project,
    get_delete_project_link,
    get_uow,
    get_update_environment,
    get_update_project,
    get_update_project_link,
)
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import (
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentUpdate,
    ProjectCreate,
    ProjectLinkCreate,
    ProjectLinkRead,
    ProjectLinkUpdate,
    ProjectRead,
    ProjectUpdate,
)
from app.modules.projects.services.create_environment import CreateEnvironment
from app.modules.projects.services.create_project import CreateProject
from app.modules.projects.services.create_project_link import CreateProjectLink
from app.modules.projects.services.delete_environment import DeleteEnvironment
from app.modules.projects.services.delete_project import DeleteProject
from app.modules.projects.services.delete_project_link import DeleteProjectLink
from app.modules.projects.services.update_environment import UpdateEnvironment
from app.modules.projects.services.update_project import UpdateProject
from app.modules.projects.services.update_project_link import UpdateProjectLink
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["projects"])


@router.post("/projects")
async def create_project(
    body: ProjectCreate,
    use_case: CreateProject = Depends(get_create_project),
    user: UserRead = Depends(require_permission("project", "create")),
) -> ApiResponse[ProjectRead]:
    """Create a new project — auto-attaches the configured default Jira/Git links."""
    project = await use_case.execute(body.name, body.description, actor_id=user.id, actor_email=user.email)
    return ApiResponse[ProjectRead](success=True, data=project)


@router.get("/projects")
async def list_projects(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("project", "read")),
) -> ApiResponse[Page[ProjectRead]]:
    """List projects."""
    items, total = await uow.projects.list_page(pagination.limit, pagination.offset)
    page = Page[ProjectRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[ProjectRead]](success=True, data=page)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("project", "read")),
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
    user: UserRead = Depends(require_permission("project", "update")),
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
    user: UserRead = Depends(require_permission("project", "delete")),
) -> ApiResponse[None]:
    """Delete a project. Its environments and links cascade at the DB level."""
    await use_case.execute(project_id, actor_id=user.id, actor_email=user.email)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/environments")
async def list_environments(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("environment", "read")),
) -> ApiResponse[list[EnvironmentRead]]:
    """List a project's environments."""
    environments = await uow.environments.list_for_project(project_id)
    return ApiResponse[list[EnvironmentRead]](success=True, data=environments)


@router.post("/projects/{project_id}/environments")
async def create_environment(
    project_id: UUID,
    body: EnvironmentCreate,
    use_case: CreateEnvironment = Depends(get_create_environment),
    user: UserRead = Depends(require_permission("environment", "create")),
) -> ApiResponse[EnvironmentRead]:
    """Create an environment. Rejected if the project already has one of this type."""
    env = await use_case.execute(
        project_id, body.type, body.name, body.base_url, actor_id=user.id, actor_email=user.email
    )
    return ApiResponse[EnvironmentRead](success=True, data=env)


@router.patch("/environments/{environment_id}")
async def update_environment(
    environment_id: UUID,
    body: EnvironmentUpdate,
    use_case: UpdateEnvironment = Depends(get_update_environment),
    user: UserRead = Depends(require_permission("environment", "update")),
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
    user: UserRead = Depends(require_permission("environment", "delete")),
) -> ApiResponse[None]:
    """Delete an environment."""
    await use_case.execute(environment_id, actor_id=user.id, actor_email=user.email)
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/links")
async def list_project_links(
    project_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("project", "read")),
) -> ApiResponse[list[ProjectLinkRead]]:
    """List a project's external links."""
    links = await uow.project_links.list_for_project(project_id)
    return ApiResponse[list[ProjectLinkRead]](success=True, data=links)


@router.post("/projects/{project_id}/links")
async def create_project_link(
    project_id: UUID,
    body: ProjectLinkCreate,
    use_case: CreateProjectLink = Depends(get_create_project_link),
    _user: UserRead = Depends(require_permission("project", "update")),
) -> ApiResponse[ProjectLinkRead]:
    """Add an external link to a project."""
    link = await use_case.execute(project_id, body.type, body.name, body.url)
    return ApiResponse[ProjectLinkRead](success=True, data=link)


@router.patch("/links/{link_id}")
async def update_project_link(
    link_id: UUID,
    body: ProjectLinkUpdate,
    use_case: UpdateProjectLink = Depends(get_update_project_link),
    _user: UserRead = Depends(require_permission("project", "update")),
) -> ApiResponse[ProjectLinkRead]:
    """Rename and/or re-point a project link."""
    link = await use_case.execute(link_id, name=body.name, url=body.url)
    return ApiResponse[ProjectLinkRead](success=True, data=link)


@router.delete("/links/{link_id}")
async def delete_project_link(
    link_id: UUID,
    use_case: DeleteProjectLink = Depends(get_delete_project_link),
    _user: UserRead = Depends(require_permission("project", "update")),
) -> ApiResponse[None]:
    """Remove a project link."""
    await use_case.execute(link_id)
    return ApiResponse[None](success=True)
