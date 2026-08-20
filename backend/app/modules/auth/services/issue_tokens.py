"""Use case: issue this app's own session JWTs for a signed in user."""

import uuid
from dataclasses import dataclass

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.security import JwtCodec
from app.modules.auth.config import auth_settings
from app.modules.auth.schemas import UserRead


@dataclass(frozen=True)
class AppTokenSet:
    """This app's own access + refresh JWTs. Not a wire model — these are
    set as HttpOnly cookies by the router, never returned in a JSON body."""

    access_token: str
    refresh_token: str


class IssueTokens(AbstractUseCase):
    """Build the two-tier session's app-level tokens (docs/tasks/sso-login.md #7).

    Independent of DX's own tokens (see app.integrations.dx_core.repository),
    which are stored server side and never leave the backend.
    """

    @use_case
    async def execute(self, user: UserRead) -> AppTokenSet:
        access = JwtCodec.encode(
            {"sub": str(user.id), "role": user.role.value, "type": "access", "jti": uuid.uuid4().hex},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=auth_settings.ACCESS_TOKEN_TTL_SECONDS,
        )
        refresh = JwtCodec.encode(
            {"sub": str(user.id), "type": "refresh", "jti": uuid.uuid4().hex},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=auth_settings.REFRESH_TOKEN_TTL_SECONDS,
        )
        return AppTokenSet(access_token=access, refresh_token=refresh)
