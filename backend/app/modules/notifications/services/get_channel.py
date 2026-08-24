from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork


class GetNotificationChannel(AbstractUseCase):
    def __init__(self, uow: AbstractNotificationsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, channel_id: UUID) -> NotificationChannelRead:
        channel = await self._uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()
        return channel
