"""Update a notification channel. Every field is optional at this layer —
an omitted field keeps its existing value, mirroring UpdateCloudflareAccount's
label/api_token convention. `type` is immutable, matching record_type's
immutability precedent from Phase 4's DNS records."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.constants import NotificationsAuditActions
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.rules import NotificationRules
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.users.public import UserRead


class UpdateNotificationChannel(AbstractUseCase):
    def __init__(self, uow: AbstractNotificationsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        channel_id: UUID,
        *,
        name: str | None = None,
        config: dict | None = None,
        is_active: bool | None = None,
        actor: UserRead,
    ) -> NotificationChannelRead:
        existing = await self._uow.channels.get_by_id(channel_id)
        if existing is None:
            raise NotificationChannelNotFound()

        if config is not None:
            NotificationRules.validate_config(existing.type, config)

        channel = await self._uow.channels.update(channel_id, name=name, config=config, is_active=is_active)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=NotificationsAuditActions.CHANNEL_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Notification channel '{channel.name}' updated",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            project_id=channel.project_id,
            environment_id=channel.environment_id,
        )
        return channel
