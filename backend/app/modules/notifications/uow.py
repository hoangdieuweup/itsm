"""Transaction boundary for the notifications module."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.modules.notifications.repository import (
    AbstractNotificationChannelRepository,
    NotificationChannelRepository,
)

logger = logging.getLogger(__name__)


class AbstractNotificationsUnitOfWork(AbstractUnitOfWork):
    channels: AbstractNotificationChannelRepository


class NotificationsUnitOfWork(AbstractNotificationsUnitOfWork):
    """No cache invalidation plumbing — same low-traffic reasoning as
    observability/uow.py's ObservabilityUnitOfWork."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.channels = NotificationChannelRepository(session)

    @database
    async def commit(self) -> None:
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        await self._session.rollback()
        logger.warning("notifications unit of work rolled back")
