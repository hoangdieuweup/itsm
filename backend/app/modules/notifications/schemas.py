from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.models import CustomModel, FrozenModel
from app.modules.notifications.constants import NotificationChannelType, NotificationsLimits


class NotificationChannelRead(FrozenModel):
    id: UUID
    project_id: UUID
    environment_id: UUID | None
    type: NotificationChannelType
    name: str
    config: dict
    """Type-appropriate masked view, never the raw stored JSON — see
    NotificationChannelRepository's read-mapping for what each type
    actually exposes."""
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationChannelCreate(CustomModel):
    project_id: UUID
    environment_id: UUID | None = None
    type: NotificationChannelType
    name: str = Field(max_length=NotificationsLimits.MAX_NAME_LENGTH)
    config: dict


class NotificationChannelUpdate(CustomModel):
    name: str | None = Field(default=None, max_length=NotificationsLimits.MAX_NAME_LENGTH)
    config: dict | None = None
    is_active: bool | None = None


class TestSendRequest(CustomModel):
    message: str | None = Field(default=None, max_length=NotificationsLimits.MAX_TEST_MESSAGE_LENGTH)
