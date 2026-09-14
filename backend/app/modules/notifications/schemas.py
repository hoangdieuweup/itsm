from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.models import CustomModel, FrozenModel
from app.modules.notifications.constants import (
    NotificationChannelType,
    NotificationKind,
    NotificationsLimits,
)


class NotificationEvent(FrozenModel):
    """What happened, in the shape the templates render. Every field beyond kind
    and title is optional: a test-send event carries only a title, while an
    incident carries everything the email table shows."""

    kind: NotificationKind
    title: str
    severity: str | None = None
    category: str | None = None
    source: str | None = None
    detected_at: datetime | None = None
    project_name: str | None = None
    environment_name: str | None = None
    rule_name: str | None = None
    incident_url: str | None = None


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
