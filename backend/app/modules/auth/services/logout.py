"""Use case: revoke the DX link and blacklist this app's own session tokens."""

from datetime import UTC, datetime

import jwt

from app.core.base.markers import helper, use_case
from app.core.base.use_case import AbstractUseCase
from app.core.security import JwtCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCacheNamespaces


class LogoutUser(AbstractUseCase):
    """Best-effort revoke at DX, then blacklist the caller's own session tokens
    (docs/tasks/sso-login.md #10) so a stolen-but-not-yet-expired cookie can't
    keep working after logout.

    DX revoke is best-effort by design: DxCoreClient.revoke() already
    swallows any DX outage internally (see its own docstring), so a user is
    never stuck signed in locally just because DX is unreachable.
    """

    def __init__(
        self, dx_tokens: AbstractDxTokenRepository, dx_client: DxCoreClient, cache: CacheClient
    ) -> None:
        self._dx_tokens = dx_tokens
        self._dx_client = dx_client
        self._cache = cache

    @use_case
    async def execute(self, user_id: int, access_token: str | None, refresh_token: str | None) -> None:
        row = await self._dx_tokens.get_by_user_id(user_id)
        if row is not None:
            await self._dx_client.revoke(self._dx_tokens.decrypt_access_token(row))
        await self._dx_tokens.clear(user_id)

        for raw in (access_token, refresh_token):
            if raw is not None:
                await self._blacklist(raw)

    @helper
    async def _blacklist(self, raw_token: str) -> None:
        """Store a revocation marker until the token would have expired anyway.

        An already-expired or unparsable token is skipped: its own exp claim
        already invalidates it, so no blacklist entry is needed.
        """
        try:
            claims = JwtCodec.decode(raw_token, secret=auth_settings.JWT_SECRET)
        except jwt.PyJWTError:
            return
        ttl = max(int(claims["exp"]) - int(datetime.now(UTC).timestamp()), 1)
        key = CacheKeyBuilder.session_key(AuthCacheNamespaces.TOKEN_BLACKLIST, claims["jti"])
        await self._cache.set_json(key, {"revoked": True}, ttl=ttl)
