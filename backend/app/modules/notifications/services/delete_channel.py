from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.constants import NotificationsAuditActions
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.users.public import UserRead


class DeleteNotificationChannel(AbstractUseCase):
    def __init__(self, uow: AbstractNotificationsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, channel_id: UUID, *, actor: UserRead) -> None:
        existing = await self._uow.channels.get_by_id(channel_id)
        if existing is None:
            raise NotificationChannelNotFound()

        await self._uow.channels.delete(channel_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=NotificationsAuditActions.CHANNEL_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Notification channel '{existing.name}' deleted",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            project_id=existing.project_id,
            environment_id=existing.environment_id,
        )
