"""Send a message through one channel — dispatches on channel.type to the
one client that knows how to send through it, the only place in this module
that does. Extracted from TestSendNotificationChannel's private _dispatch so
both the test-send endpoint and cross-module incident notifications
(observability, Phase 9) share one implementation, never two."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.email.client import EmailClient
from app.integrations.email.config import email_settings
from app.integrations.telegram.client import TelegramClient
from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import SmtpNotConfigured, UnsupportedChannelType
from app.modules.notifications.rules import NotificationRules
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork


class DispatchNotification(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractNotificationsUnitOfWork,
        *,
        telegram_client: TelegramClient,
        email_client: EmailClient,
        base_vn_client: BaseVnClient,
    ) -> None:
        self._uow = uow
        self._telegram_client = telegram_client
        self._email_client = email_client
        self._base_vn_client = base_vn_client

    @use_case
    async def execute(self, channel: NotificationChannelRead, text: str) -> None:
        if channel.type == NotificationChannelType.OTHER:
            raise UnsupportedChannelType()

        raw_config = await self._uow.channels.get_config_ciphertext_fields(channel.id)

        if channel.type == NotificationChannelType.TELEGRAM:
            bot_token = FernetCodec.decrypt(raw_config["bot_token"], key=notifications_settings.FERNET_KEY)
            await self._telegram_client.send_message(
                bot_token=bot_token, chat_id=raw_config["chat_id"], text=text
            )
        elif channel.type == NotificationChannelType.EMAIL:
            if not email_settings.SMTP_HOST:
                raise SmtpNotConfigured()
            await self._email_client.send(
                recipients=raw_config["recipients"], subject="ITSM Notification", body=text
            )
        elif channel.type == NotificationChannelType.BASE_VN:
            webhook_url = FernetCodec.decrypt(
                raw_config["webhook_url"], key=notifications_settings.FERNET_KEY
            )
            content = NotificationRules.render_base_content(raw_config.get("message_template", ""), text)
            await self._base_vn_client.send(webhook_url=webhook_url, base_content=content)
