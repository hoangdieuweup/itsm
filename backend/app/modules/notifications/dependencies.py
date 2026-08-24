"""FastAPI dependency providers for the notifications module. Every provider
depends on an Abstract* contract."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.base_vn.client import BaseVnClient
from app.integrations.base_vn.dependencies import get_base_vn_client
from app.integrations.email.client import EmailClient
from app.integrations.email.dependencies import get_email_client
from app.integrations.telegram.client import TelegramClient
from app.integrations.telegram.dependencies import get_telegram_client
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.notifications.services.create_channel import CreateNotificationChannel
from app.modules.notifications.services.delete_channel import DeleteNotificationChannel
from app.modules.notifications.services.get_channel import GetNotificationChannel
from app.modules.notifications.services.list_channels import ListNotificationChannels
from app.modules.notifications.services.test_send_channel import TestSendNotificationChannel
from app.modules.notifications.services.update_channel import UpdateNotificationChannel
from app.modules.notifications.uow import AbstractNotificationsUnitOfWork, NotificationsUnitOfWork
from app.modules.projects.public import ProjectsApi, get_projects_api


async def get_uow(session: AsyncSession = Depends(get_session)) -> NotificationsUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return NotificationsUnitOfWork(session)


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
