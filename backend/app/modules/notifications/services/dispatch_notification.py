"""Send one notification event through one channel — dispatches on channel.type
to the client that knows how to send through it, the only place in this module
that does. The event is rendered once here and each channel gets the format it
can show: an HTML body plus its text alternative for email, plain text for the
rest."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.email.client import EmailClient
from app.integrations.email.config import email_settings
from app.integrations.telegram.client import TelegramClient
from app.modules.notifications.constants import NotificationChannelType
from app.modules.notifications.exceptions import SmtpNotConfigured, UnsupportedChannelType
from app.modules.notifications.rules import NotificationRules
from app.modules.notifications.schemas import NotificationChannelRead, NotificationEvent
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.notifications.utils import NotificationTemplates


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
    async def execute(self, channel: NotificationChannelRead, event: NotificationEvent) -> None:
        if channel.type == NotificationChannelType.OTHER:
            raise UnsupportedChannelType()

        config = await self._uow.channels.get_dispatch_config(channel.id)
        text = NotificationTemplates.render_text(event)

        if channel.type == NotificationChannelType.TELEGRAM:
            await self._telegram_client.send_message(
                bot_token=config["bot_token"], chat_id=config["chat_id"], text=text
            )
        elif channel.type == NotificationChannelType.EMAIL:
            if not email_settings.SMTP_HOST:
                raise SmtpNotConfigured()
            await self._email_client.send(
                recipients=config["recipients"],
                subject=NotificationTemplates.subject(event),
                body=text,
                html=NotificationTemplates.render_html(event),
            )
        elif channel.type == NotificationChannelType.BASE_VN:
            content = NotificationRules.render_base_content(config.get("message_template", ""), text)
            await self._base_vn_client.send(webhook_url=config["webhook_url"], base_content=content)
