"""Test-send a notification channel — delegates the actual per-type dispatch
to DispatchNotification (services/dispatch_notification.py), the one place
in this module that knows how to send through a channel. This use case only
adds the test-message default and the TEST_SENT audit trail around it."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.email.client import EmailClient
from app.integrations.telegram.client import TelegramClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.constants import (
    NotificationKind,
    NotificationsAuditActions,
    NotificationsDefaults,
)
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.schemas import NotificationEvent
from app.modules.notifications.services.dispatch_notification import DispatchNotification
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.users.public import UserRead


class TestSendNotificationChannel(AbstractUseCase):
    __test__ = False

    def __init__(
        self,
        uow: AbstractNotificationsUnitOfWork,
        *,
        telegram_client: TelegramClient,
        email_client: EmailClient,
        base_vn_client: BaseVnClient,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._audit_api = audit_api
        self._dispatch_use_case = DispatchNotification(
            uow, telegram_client=telegram_client, email_client=email_client, base_vn_client=base_vn_client
        )

    @use_case
    async def execute(self, channel_id: UUID, *, message: str | None, actor: UserRead) -> None:
        channel = await self._uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()

        event = NotificationEvent(
            kind=NotificationKind.TEST, title=message or NotificationsDefaults.TEST_MESSAGE
        )
        try:
            await self._dispatch_use_case.execute(channel, event)
        finally:
            await self._audit_api.log_event(
                type=AuditEventType.AUDIT,
                source=AuditSource.USER_ACTION,
                action=NotificationsAuditActions.TEST_SENT,
                severity=AuditSeverity.INFO,
                message=f"Test-sent through notification channel '{channel.name}'",
                actor=AuditActor(user_id=actor.id, email=actor.email),
                project_id=channel.project_id,
                environment_id=channel.environment_id,
            )
