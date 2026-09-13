"""FastAPI dependency providers for the notifications module. Every provider
depends on an Abstract* contract."""

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.base_vn.dependencies import get_base_vn_client
from app.integrations.email.client import EmailClient
from app.integrations.email.dependencies import get_email_client
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.dependencies import get_telegram_client
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.notifications.exceptions import NotificationChannelNotFound, NotificationPermissionDenied
from app.modules.notifications.services.create_channel import CreateNotificationChannel
from app.modules.notifications.services.delete_channel import DeleteNotificationChannel
from app.modules.notifications.services.get_channel import GetNotificationChannel
from app.modules.notifications.services.list_channels import ListNotificationChannels
from app.modules.notifications.services.test_send_channel import TestSendNotificationChannel
from app.modules.notifications.services.update_channel import UpdateNotificationChannel
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork, NotificationsUnitOfWork
from app.modules.projects.public import ProjectsApi, get_projects_api
from app.modules.rbac.public import RbacApi, get_rbac_api
from app.modules.users.public import UserRead


async def get_uow(session: AsyncSession = Depends(get_session)) -> NotificationsUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return NotificationsUnitOfWork(session)


def require_notification_project_permission(resource: str, action: str):
    """Project-scoped permission guard keyed by project_id (query param).
    Uses ProjectsApi.resolve_effective_permissions (the facade) to check
    the caller's effective permission set (global UNION project role)."""

    async def check(
        project_id: UUID = Query(alias="projectId"),
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        projects_api: ProjectsApi = Depends(get_projects_api),
    ) -> UserRead:
        user = auth_api.current_user()
        perms = await projects_api.resolve_effective_permissions(project_id, user, rbac_api)
        if f"{resource}.{action}" not in perms:
            raise NotificationPermissionDenied()
        return user

    return check


def require_notification_channel_permission(resource: str, action: str):
    """Project-scoped permission guard keyed by channel_id (path param).
    Resolves project_id from the notification channel record via the
    notifications UoW, then delegates to ProjectsApi facade."""

    async def check(
        channel_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        projects_api: ProjectsApi = Depends(get_projects_api),
        uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    ) -> UserRead:
        user = auth_api.current_user()
        channel = await uow.channels.get_by_id(channel_id)
        if channel is None:
            raise NotificationChannelNotFound()
        perms = await projects_api.resolve_effective_permissions(channel.project_id, user, rbac_api)
        if f"{resource}.{action}" not in perms:
            raise NotificationPermissionDenied()
        return user

    return check


async def get_create_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateNotificationChannel:
    return CreateNotificationChannel(uow, projects_api, audit_api)


async def get_get_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
) -> GetNotificationChannel:
    return GetNotificationChannel(uow)


async def get_list_notification_channels(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    projects_api: ProjectsApi = Depends(get_projects_api),
) -> ListNotificationChannels:
    return ListNotificationChannels(uow, projects_api)


async def get_update_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateNotificationChannel:
    return UpdateNotificationChannel(uow, audit_api)


async def get_delete_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteNotificationChannel:
    return DeleteNotificationChannel(uow, audit_api)


async def get_test_send_notification_channel(
    uow: AbstractNotificationsUnitOfWork = Depends(get_uow),
    telegram_client: TelegramClient = Depends(get_telegram_client),
    email_client: EmailClient = Depends(get_email_client),
    base_vn_client: BaseVnClient = Depends(get_base_vn_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> TestSendNotificationChannel:
    return TestSendNotificationChannel(
        uow,
        telegram_client=telegram_client,
        email_client=email_client,
        base_vn_client=base_vn_client,
        audit_api=audit_api,
    )
