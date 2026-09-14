"""Contract exposed to other modules. Phase 9's alerting flow is the first
real cross-module consumer: it dispatches incident notifications through
whichever channels an alert rule lists, via the same DispatchNotification
use case the test-send endpoint already uses."""

from uuid import UUID

from fastapi import Depends

from app.core.base.markers import facade
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.base_vn.dependencies import get_base_vn_client
from app.integrations.email.client import EmailClient
from app.integrations.email.dependencies import get_email_client
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.dependencies import get_telegram_client
from app.modules.notifications.constants import NotificationKind, NotificationTemplateDefaults
from app.modules.notifications.dependencies import get_uow
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.schemas import NotificationEvent
from app.modules.notifications.services.dispatch_notification import DispatchNotification
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork

__all__ = [
    "NotificationEvent",
    "NotificationKind",
    "NotificationTemplateDefaults",
    "NotificationsApi",
    "get_notifications_api",
]


class NotificationsApi:
    """Facade over notification channels for other modules' cross-module needs."""

    def __init__(
        self,
        uow: AbstractNotificationsUnitOfWork,
        *,
        telegram_client: TelegramClient,
        email_client: EmailClient,
        base_vn_client: BaseVnClient,
    ) -> None:
        self._uow = uow
        self._dispatch_use_case = DispatchNotification(
            uow, telegram_client=telegram_client, email_client=email_client, base_vn_client=base_vn_client
        )

    @facade
    async def dispatch(self, channel_id: UUID, event: NotificationEvent) -> None:
        """Send `event` through channel_id, rendered into whatever that channel can
        show. Raises NotificationChannelNotFound
        if it doesn't exist, or the channel-type-specific send exception on
        failure (EmailRejected, TelegramApiUnavailable, etc.) — the caller
        decides how to handle a failed dispatch (observability's incident
        flow logs a warning and continues, never letting a broken channel
        block incident creation). This facade never swallows a failure
        itself, unlike audit.public.log_event's fire-and-forget degrade —
        a caller that genuinely needs "log and continue" makes that choice
        explicitly at its own call site."""
        channel = await self._uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()
        await self._dispatch_use_case.execute(channel, event)


async def get_notifications_api(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    telegram_client: TelegramClient = Depends(get_telegram_client),
    email_client: EmailClient = Depends(get_email_client),
    base_vn_client: BaseVnClient = Depends(get_base_vn_client),
) -> NotificationsApi:
    """Provide the facade to other modules."""
    return NotificationsApi(
        uow, telegram_client=telegram_client, email_client=email_client, base_vn_client=base_vn_client
    )
