"""Schemas for the users module."""

from datetime import datetime

from app.core.models import FrozenModel
from app.modules.users.constants import UserStatus


class UserRead(FrozenModel):
    """Representation safe to round trip through the cache. Never includes DX tokens."""

    id: int
    email: str
    name: str
    status: UserStatus
    external_user_id: str | None
    employee_code: str | None
    email_confirmed: bool
    last_login_at: datetime | None
    created_at: datetime


class UserStatusUpdate(FrozenModel):
    """Request body for PATCH /users/{id}/status."""

    status: UserStatus
