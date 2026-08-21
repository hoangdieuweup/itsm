"""Schemas for the auth module."""

from app.core.models import FrozenModel
from app.modules.users.public import UserRead


class MeResponse(FrozenModel):
    """/me's response: the user's profile plus their resolved role/permissions."""

    user: UserRead
    role_name: str
    permissions: list[str]
