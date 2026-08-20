"""Schemas for the auth module."""

from datetime import datetime

from app.core.models import FrozenModel
from app.modules.auth.constants import UserRole, UserStatus


class DepartmentRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: int
    code: str
    name: str


class UserRead(FrozenModel):
    """Representation safe to round trip through the cache. Never includes DX tokens."""

    id: int
    email: str
    name: str
    role: UserRole
    status: UserStatus
    department_id: int | None
    external_user_id: str | None
    employee_code: str | None
    email_confirmed: bool
    last_login_at: datetime | None
    created_at: datetime
