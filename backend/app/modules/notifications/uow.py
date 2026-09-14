"""Transaction boundary for the notifications module."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.uow import AbstractUnitOfWork
from app.core.uow import SqlAlchemyUnitOfWork
from app.modules.notifications.repository import (
    AbstractNotificationChannelRepository,
    NotificationChannelRepository,
)


class AbstractNotificationsUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    channels: AbstractNotificationChannelRepository


class NotificationsUnitOfWork(AbstractNotificationsUnitOfWork, SqlAlchemyUnitOfWork):
    """No cache invalidation plumbing — same low-traffic reasoning as
    observability/uow.py's ObservabilityUnitOfWork."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.channels = NotificationChannelRepository(session)
