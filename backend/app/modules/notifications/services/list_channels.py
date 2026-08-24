from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.notifications.exceptions import NotificationsProjectNotFound
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.projects.public import ProjectsApi


class ListNotificationChannels(AbstractUseCase):
    def __init__(self, uow: AbstractNotificationsUnitOfWork, projects_api: ProjectsApi) -> None:
        self._uow = uow
        self._projects_api = projects_api

    @use_case
    async def execute(
        self, project_id: UUID, *, environment_id: UUID | None
    ) -> list[NotificationChannelRead]:
        if await self._projects_api.get_project_by_id(project_id) is None:
            raise NotificationsProjectNotFound()
        return await self._uow.channels.list_for_project(project_id, environment_id=environment_id)
