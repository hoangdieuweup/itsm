"""Schemas for the auth module."""

from app.core.models import FrozenModel
from app.modules.users.public import UserRead


class MeResponse(FrozenModel):
    """/me's response: the user's profile plus their resolved roles/permissions."""

    user: UserRead
    role_names: list[str] = []
    roles: list[str] = []
    role_name: str | None = None
    permissions: list[str] = []
