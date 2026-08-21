"""Contract exposed to other modules. This is the ONLY file another module
may import from projects — enforced by scripts/check_module_boundaries.py.
"""

from uuid import UUID

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.projects.dependencies import get_uow
from app.modules.projects.schemas import EnvironmentRead, ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork

__all__ = ["ProjectRead", "EnvironmentRead", "ProjectsApi", "get_projects_api"]


class ProjectsApi:
    """Facade over projects/environments for other modules' cross-module needs:
    Cloudflare/observability/notifications validating an environment_id (and,
    transitively, the project it belongs to) before creating their own rows."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @facade
    async def get_project_by_id(self, project_id: UUID) -> ProjectRead | None:
        """Look up any project by id — for a single existence check from
        another module, never for bulk reads."""
        return await self._uow.projects.get_by_id(project_id)

    @facade
    async def get_environment_by_id(self, environment_id: UUID) -> EnvironmentRead | None:
        """Look up any environment by id — for another module to validate
        an environment_id foreign key before writing its own row."""
        return await self._uow.environments.get_by_id(environment_id)


async def get_projects_api(uow: AbstractProjectsUnitOfWork = Depends(get_uow)) -> ProjectsApi:
    """Provide the facade to other modules."""
    return ProjectsApi(uow)
