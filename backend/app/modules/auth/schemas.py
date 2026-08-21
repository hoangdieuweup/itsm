"""Schemas for the auth module."""

from datetime import datetime

from app.core.models import FrozenModel
from app.modules.auth.constants import UserStatus


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


class MeResponse(FrozenModel):
    """/me's response: the user's profile plus their resolved role/permissions."""

    user: UserRead
    role_name: str
    permissions: list[str]


class UserStatusUpdate(FrozenModel):
    """Request body for PATCH /auth/users/{id}/status."""

    status: UserStatus
