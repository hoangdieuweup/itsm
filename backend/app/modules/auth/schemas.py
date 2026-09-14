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


class LogoutRequest(FrozenModel):
    """/logout's optional body. end_dx_session also ends the browser's WeUp DX SSO session."""

    end_dx_session: bool = False


class LogoutResponse(FrozenModel):
    """/logout's response. dx_logout_url is where the browser goes next to end its WeUp DX
    SSO session, or None when only this app's session was ended."""

    dx_logout_url: str | None = None
