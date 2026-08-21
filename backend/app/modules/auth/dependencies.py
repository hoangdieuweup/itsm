"""Dependency wiring for the auth module.

The composition root: the only place that names a concrete class
(AuthUnitOfWork, DxTokenRepository, ...) instead of its Abstract* contract.
See references/layer-examples.md.

Deliberately imports nothing from rbac: get_authenticate_with_dx and
get_update_user_status need RbacApi (rbac.public), and rbac.public needs
auth.public, which needs get_current_user/get_uow from this very file — so
those two factory functions live in auth/router.py instead, which is never
imported by anything else and can safely reach into rbac.public without
closing that cycle. See auth/router.py's and rbac/public.py's docstrings.
"""

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import JwtCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.dependencies import get_dx_core_client
from app.integrations.dx_core.repository import AbstractDxTokenRepository, DxTokenRepository
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCacheNamespaces, AuthCookies
from app.modules.auth.exceptions import NotAuthenticated, UserBlocked, UserNotFound
from app.modules.auth.rules import AuthRules
from app.modules.auth.schemas import UserRead
from app.modules.auth.services.issue_tokens import IssueTokens
from app.modules.auth.services.logout import LogoutUser
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork, AuthUnitOfWork


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> AuthUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return AuthUnitOfWork(session, cache)


async def get_dx_token_repository(
    session: AsyncSession = Depends(get_session),
) -> AbstractDxTokenRepository:
    """Provide the DX token repository, sharing this request's session/transaction
    with get_uow (both resolve from the same cached get_session dependency)."""
    return DxTokenRepository(session)


async def get_current_user(
    request: Request,
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    cache: CacheClient = Depends(get_cache),
) -> UserRead:
    """Resolve the signed in user from the access_token session cookie.

    Rejects a token that decodes fine but was blacklisted by a prior
    /auth/logout call (app/modules/auth/services/logout.py) — expiry alone
    isn't enough once a user can end a session early.
    """
    raw = request.cookies.get(AuthCookies.ACCESS_TOKEN)
    if raw is None:
        raise NotAuthenticated()
    try:
        claims = JwtCodec.decode(raw, secret=auth_settings.JWT_SECRET)
    except jwt.PyJWTError as exc:
        raise NotAuthenticated() from exc
    if claims.get("type") != "access":
        raise NotAuthenticated()

    blacklist_key = CacheKeyBuilder.session_key(AuthCacheNamespaces.TOKEN_BLACKLIST, claims["jti"])
    if await cache.get_json(blacklist_key) is not None:
        raise NotAuthenticated()

    user = await uow.users.get_by_id(int(claims["sub"]))
    if user is None:
        raise UserNotFound()
    if not AuthRules.can_login(user.status):
        raise UserBlocked()
    return user


async def require_auth(user: UserRead = Depends(get_current_user)) -> UserRead:
    """Guard a route behind an authenticated session."""
    return user


async def get_sync_external_user(uow: AbstractAuthUnitOfWork = Depends(get_uow)) -> SyncExternalUser:
    """Provide the DX profile sync use case."""
    return SyncExternalUser(uow)


async def get_issue_tokens() -> IssueTokens:
    """Provide the app session token issuance use case."""
    return IssueTokens()


async def get_logout_user(
    dx_tokens: AbstractDxTokenRepository = Depends(get_dx_token_repository),
    dx_client: DxCoreClient = Depends(get_dx_core_client),
    cache: CacheClient = Depends(get_cache),
) -> LogoutUser:
    """Provide the logout use case."""
    return LogoutUser(dx_tokens, dx_client, cache)
