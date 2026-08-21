from datetime import UTC, datetime
from uuid import UUID

import jwt

from app.core.base.markers import helper, use_case
from app.core.base.use_case import AbstractUseCase
from app.core.security import JwtCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.keys import CacheKeyBuilder
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCacheNamespaces, TokenType
from app.modules.auth.exceptions import NotAuthenticated, UserBlocked
from app.modules.auth.rules import AuthRules
from app.modules.auth.services.issue_tokens import AppTokenSet, IssueTokens
from app.modules.users.public import UsersApi


class RefreshToken(AbstractUseCase):
    """Refreshes the session token pair with rotation and blacklist check."""

    def __init__(
        self,
        users_api: UsersApi,
        issue_tokens: IssueTokens,
        cache: CacheClient,
    ) -> None:
        self._users_api = users_api
        self._issue_tokens = issue_tokens
        self._cache = cache

    @use_case
    async def execute(self, raw_refresh_token: str | None) -> AppTokenSet:
        if raw_refresh_token is None:
            raise NotAuthenticated()

        try:
            claims = JwtCodec.decode(raw_refresh_token, secret=auth_settings.JWT_SECRET)
        except jwt.PyJWTError as exc:
            raise NotAuthenticated() from exc

        if claims.get("type") != TokenType.REFRESH:
            raise NotAuthenticated()

        blacklist_key = CacheKeyBuilder.session_key(
            AuthCacheNamespaces.TOKEN_BLACKLIST, str(claims["jti"])
        )
        if await self._cache.get_json(blacklist_key) is not None:
            raise NotAuthenticated()

        user = await self._users_api.get_user_by_id(UUID(str(claims["sub"])))
        if user is None:
            raise NotAuthenticated()
        if not AuthRules.can_login(user.status):
            raise UserBlocked()

        # Token rotation: Blacklist old refresh token
        await self._blacklist(claims)

        # Issue fresh token set (access + refresh)
        return await self._issue_tokens.execute(user)

    @helper
    async def _blacklist(self, claims: dict[str, object]) -> None:
        """Blacklist the old refresh token jti to prevent replay attacks."""
        exp = claims.get("exp")
        if isinstance(exp, (int, float)):
            ttl = max(int(exp) - int(datetime.now(UTC).timestamp()), 1)
        else:
            ttl = auth_settings.REFRESH_TOKEN_TTL_SECONDS
        key = CacheKeyBuilder.session_key(
            AuthCacheNamespaces.TOKEN_BLACKLIST, str(claims["jti"])
        )
        await self._cache.set_json(key, {"revoked": True}, ttl=ttl)
