from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.constants import ProjectLinkType
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectLinkRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateProjectLink(AbstractUseCase):
    """Create a project link. Always is_default=False — only CreateProject's
    seeded rows are marked default."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, project_id: UUID, type: ProjectLinkType, name: str, url: str) -> ProjectLinkRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        link = await self._uow.project_links.create(
            project_id=project_id, type=type, name=name, url=url, is_default=False
        )
        await self._uow.commit()
        return link
