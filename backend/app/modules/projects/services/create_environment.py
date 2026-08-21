from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.constants import EnvironmentType
from app.modules.projects.exceptions import EnvironmentTypeAlreadyExists, ProjectNotFound
from app.modules.projects.schemas import EnvironmentRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateEnvironment(AbstractUseCase):
    """Create an environment. Rejected if the project doesn't exist, or already
    has an environment of the requested type (UNIQUE(project_id, type))."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(
        self, project_id: UUID, type: EnvironmentType, name: str, base_url: str | None
    ) -> EnvironmentRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        if await self._uow.environments.find_by_project_and_type(project_id, type) is not None:
            raise EnvironmentTypeAlreadyExists()
        env = await self._uow.environments.create(project_id=project_id, type=type, name=name, base_url=base_url)
        await self._uow.commit()
        return env
