from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectLinkNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteProjectLink(AbstractUseCase):
    """Delete a project link."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, link_id: UUID) -> None:
        if await self._uow.project_links.get_by_id(link_id) is None:
            raise ProjectLinkNotFound()
        await self._uow.project_links.delete(link_id)
        await self._uow.commit()
