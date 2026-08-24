"""Test-send a notification channel — dispatches on channel.type to the one
client that knows how to send through it, the only place in this module
that does."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.email.client import EmailClient
from app.integrations.telegram.client import TelegramClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelType, NotificationsAuditActions
from app.modules.notifications.exceptions import NotificationChannelNotFound, UnsupportedChannelType
from app.modules.notifications.rules import NotificationRules
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.users.public import UserRead

_DEFAULT_TEST_MESSAGE = "Test notification from ITSM"


class TestSendNotificationChannel(AbstractUseCase):
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
        self._telegram_client = telegram_client
        self._email_client = email_client
        self._base_vn_client = base_vn_client
        self._audit_api = audit_api

    @use_case
    async def execute(self, channel_id: UUID, *, message: str | None, actor: UserRead) -> None:
        channel = await self._uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()

        text = message or _DEFAULT_TEST_MESSAGE
        try:
            await self._dispatch(channel, text)
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

    async def _dispatch(self, channel: NotificationChannelRead, text: str) -> None:
        if channel.type == NotificationChannelType.OTHER:
            raise UnsupportedChannelType()

        raw_config = await self._uow.channels.get_config_ciphertext_fields(channel.id)

        if channel.type == NotificationChannelType.TELEGRAM:
            bot_token = FernetCodec.decrypt(raw_config["bot_token"], key=notifications_settings.FERNET_KEY)
            await self._telegram_client.send_message(
                bot_token=bot_token, chat_id=raw_config["chat_id"], text=text
            )
        elif channel.type == NotificationChannelType.EMAIL:
            await self._email_client.send(
                recipients=raw_config["recipients"], subject="ITSM Test Notification", body=text
            )
        elif channel.type == NotificationChannelType.BASE_VN:
            webhook_url = FernetCodec.decrypt(
                raw_config["webhook_url"], key=notifications_settings.FERNET_KEY
            )
            content = NotificationRules.render_base_content(raw_config.get("message_template", ""), text)
            await self._base_vn_client.send(webhook_url=webhook_url, base_content=content)
