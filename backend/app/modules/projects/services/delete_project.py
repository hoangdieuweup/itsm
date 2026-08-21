from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteProject(AbstractUseCase):
    """Delete a project. Its environments and links cascade at the DB level (ondelete=CASCADE)."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, project_id: UUID) -> None:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        await self._uow.projects.delete(project_id)
        await self._uow.commit()
