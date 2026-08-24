from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.notifications.constants import NotificationChannelType, NotificationsAuditActions
from app.modules.notifications.exceptions import (
    NotificationsEnvironmentNotFound,
    NotificationsProjectNotFound,
)
from app.modules.notifications.rules import NotificationRules
from app.modules.notifications.schemas import NotificationChannelRead
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead


class CreateNotificationChannel(AbstractUseCase):
    def __init__(
        self, uow: AbstractNotificationsUnitOfWork, projects_api: ProjectsApi, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        *,
        project_id: UUID,
        environment_id: UUID | None,
        type: NotificationChannelType,
        name: str,
        config: dict,
        actor: UserRead,
    ) -> NotificationChannelRead:
        if await self._projects_api.get_project_by_id(project_id) is None:
            raise NotificationsProjectNotFound()
        if (
            environment_id is not None
            and await self._projects_api.get_environment_by_id(environment_id) is None
        ):
            raise NotificationsEnvironmentNotFound()

        NotificationRules.validate_config(type, config)

        channel = await self._uow.channels.create(
            project_id=project_id, environment_id=environment_id, type=type, name=name, config=config
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=NotificationsAuditActions.CHANNEL_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Notification channel '{name}' created",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            project_id=project_id,
            environment_id=environment_id,
        )
        return channel
