"""HTTP layer for the notifications module. Thin: parses the request,
delegates to a use case, wraps the result in ApiResponse."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.models import ApiResponse
from app.modules.notifications.dependencies import (
    get_create_notification_channel,
    get_delete_notification_channel,
    get_get_notification_channel,
    get_list_notification_channels,
    get_test_send_notification_channel,
    get_update_notification_channel,
)
from app.modules.notifications.schemas import (
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
    TestSendRequest,
)
from app.modules.notifications.services.create_channel import CreateNotificationChannel
from app.modules.notifications.services.delete_channel import DeleteNotificationChannel
from app.modules.notifications.services.get_channel import GetNotificationChannel
from app.modules.notifications.services.list_channels import ListNotificationChannels
from app.modules.notifications.services.test_send_channel import TestSendNotificationChannel
from app.modules.notifications.services.update_channel import UpdateNotificationChannel
from app.modules.rbac.public import RbacActions, RbacResources, require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["notifications"])


@router.post("/notification-channels")
async def create_notification_channel(
    body: NotificationChannelCreate,
    use_case: CreateNotificationChannel = Depends(get_create_notification_channel),
    user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.CREATE)),
) -> ApiResponse[NotificationChannelRead]:
    channel = await use_case.execute(**body.model_dump(), actor=user)
    return ApiResponse[NotificationChannelRead](success=True, data=channel)


@router.get("/notification-channels")
async def list_notification_channels(
    project_id: UUID = Query(alias="projectId"),
    environment_id: UUID | None = Query(default=None, alias="environmentId"),
    use_case: ListNotificationChannels = Depends(get_list_notification_channels),
    _user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.READ)),
) -> ApiResponse[list[NotificationChannelRead]]:
    channels = await use_case.execute(project_id, environment_id=environment_id)
    return ApiResponse[list[NotificationChannelRead]](success=True, data=channels)


@router.get("/notification-channels/{channel_id}")
async def get_notification_channel(
    channel_id: UUID,
    use_case: GetNotificationChannel = Depends(get_get_notification_channel),
    _user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.READ)),
) -> ApiResponse[NotificationChannelRead]:
    channel = await use_case.execute(channel_id)
    return ApiResponse[NotificationChannelRead](success=True, data=channel)


@router.patch("/notification-channels/{channel_id}")
async def update_notification_channel(
    channel_id: UUID,
    body: NotificationChannelUpdate,
    use_case: UpdateNotificationChannel = Depends(get_update_notification_channel),
    user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.UPDATE)),
) -> ApiResponse[NotificationChannelRead]:
    channel = await use_case.execute(channel_id, **body.model_dump(exclude_unset=True), actor=user)
    return ApiResponse[NotificationChannelRead](success=True, data=channel)


@router.delete("/notification-channels/{channel_id}")
async def delete_notification_channel(
    channel_id: UUID,
    use_case: DeleteNotificationChannel = Depends(get_delete_notification_channel),
    user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.DELETE)),
) -> ApiResponse[None]:
    await use_case.execute(channel_id, actor=user)
    return ApiResponse[None](success=True, data=None)


@router.post("/notification-channels/{channel_id}/test-send")
async def test_send_notification_channel(
    channel_id: UUID,
    body: TestSendRequest,
    use_case: TestSendNotificationChannel = Depends(get_test_send_notification_channel),
    user: UserRead = Depends(require_permission(RbacResources.NOTIFICATION_CHANNEL, RbacActions.UPDATE)),
) -> ApiResponse[None]:
    """UPDATE-gated, not READ — exercises the channel's real stored secret
    to send a real external message."""
    await use_case.execute(channel_id, message=body.message, actor=user)
    return ApiResponse[None](success=True, data=None)
