from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateProject(AbstractUseCase):
    """Rename and/or redescribe a project."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, project_id: UUID, *, name: str | None, description: str | None) -> ProjectRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        updated = await self._uow.projects.update(project_id, name=name, description=description)
        await self._uow.commit()
        return updated
