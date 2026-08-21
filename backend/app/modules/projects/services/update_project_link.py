from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectLinkNotFound
from app.modules.projects.schemas import ProjectLinkRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateProjectLink(AbstractUseCase):
    """Rename and/or re-point a project link."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, link_id: UUID, *, name: str | None, url: str | None) -> ProjectLinkRead:
        if await self._uow.project_links.get_by_id(link_id) is None:
            raise ProjectLinkNotFound()
        updated = await self._uow.project_links.update(link_id, name=name, url=url)
        await self._uow.commit()
        return updated
