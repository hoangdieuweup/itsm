import logging
from datetime import UTC, datetime
from uuid import UUID

import jwt

from app.core.base.markers import helper, use_case
from app.core.base.use_case import AbstractUseCase
from app.core.security import JwtCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.dx_core.client import DxCoreClient
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCacheNamespaces
from app.modules.auth.exceptions import DxTokenUnreadable
from app.modules.auth.models import DxToken
from app.modules.auth.uow import AbstractAuthUnitOfWork

logger = logging.getLogger(__name__)


class LogoutUser(AbstractUseCase):
    """Revoke the stored DX tokens, clear them, then blacklist the caller's own
    session tokens (docs/tasks/sso-login.md #10) so a stolen-but-not-yet-expired
    cookie can't keep working after logout.

    Both DX tokens are revoked, refresh token first: DX's /oauth2/revoke only
    blacklists an access token's jti, so the seven-day refresh token stays
    usable unless it is revoked on its own. Revocation is best-effort by
    design — DxCoreClient.revoke() swallows any DX outage — so a user is never
    stuck signed in locally just because DX is unreachable.

    Ending the browser's DX SSO session needs the browser itself (DX reads its
    sso_sid cookie), so when asked this only returns the DX logout URL for the
    client to navigate to.
    """

    def __init__(self, uow: AbstractAuthUnitOfWork, dx_client: DxCoreClient, cache: CacheClient) -> None:
        self._uow = uow
        self._dx_client = dx_client
        self._cache = cache

    @use_case
    async def execute(
        self,
        user_id: UUID,
        access_token: str | None,
        refresh_token: str | None,
        *,
        end_dx_session: bool = False,
    ) -> str | None:
        """Return the DX logout URL when end_dx_session is set, otherwise None."""
        row = await self._uow.dx_tokens.get_by_user_id(user_id)
        if row is not None:
            await self._revoke_at_dx(row)
        await self._uow.dx_tokens.clear(user_id)
        await self._uow.commit()

        for raw in (access_token, refresh_token):
            if raw is not None:
                await self._blacklist(raw)

        return self._dx_client.build_logout_url() if end_dx_session else None

    @helper
    async def _revoke_at_dx(self, row: DxToken) -> None:
        """Revoke the stored refresh token, then the access token. Skipped when they can't
        be decrypted (saved under an earlier key, so nothing usable is left to send to DX)
        rather than failing the logout."""
        try:
            refresh = self._uow.dx_tokens.decrypt_refresh_token(row)
            access = self._uow.dx_tokens.decrypt_access_token(row)
        except DxTokenUnreadable:
            logger.warning("dx tokens unreadable at logout, skipping DX revoke user_id=%s", row.user_id)
            return
        await self._dx_client.revoke(refresh)
        await self._dx_client.revoke(access)

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
