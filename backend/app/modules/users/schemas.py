"""Schemas for the users module."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.models import FrozenModel
from app.modules.common.constants import UserStatus


class UserRead(FrozenModel):
    """Representation safe to round trip through the cache. Never includes DX tokens."""

    id: UUID
    email: str
    name: str
    status: UserStatus
    external_user_id: str | None = None
    employee_code: str | None = None
    email_confirmed: bool = False
    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    role_names: list[str] = []
    role_name: str | None = None


class UserStatusUpdate(FrozenModel):
    """Request body for PATCH /users/{id}/status."""

    status: UserStatus
