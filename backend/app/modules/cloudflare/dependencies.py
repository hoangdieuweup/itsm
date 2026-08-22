"""FastAPI dependency providers for the cloudflare module. Every provider
depends on an Abstract* contract."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.exceptions import InsufficientAccountAccess
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.schemas import AccountAccessGrant
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork, CloudflareUnitOfWork
from app.modules.rbac.public import RbacApi, get_rbac_api


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> CloudflareUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return CloudflareUnitOfWork(session, cache)


async def get_cloudflare_client() -> CloudflareClient:
    """Provide the Cloudflare API client. No transport override in production."""
    return CloudflareClient()


def require_account_access(min_level: AccessLevel):
    """Return a dependency that 403s unless the current user's per-account
    access_level (cloudflare_account_managers) meets min_level, OR they hold
    the cloudflare_account:manage_all Layer-1 permission. Returns the
    resolved AccountAccessGrant rather than a bare UserRead — callers that
    need a stricter, request-body-dependent check (UpdateCloudflareAccount's
    OWNER-for-token-rotation rule) re-validate the grant themselves instead
    of this being expressible as a second static Depends factory."""

    async def check(
        account_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    ) -> AccountAccessGrant:
        user = auth_api.current_user()
        if await rbac_api.has_permission(user.id, "cloudflare_account", "manage_all"):
            return AccountAccessGrant(user=user, held_level=None)

        manager_row = await uow.account_managers.get_for_user(account_id, user.id)
        # IMPORTANT: do not funnel "no row" through satisfies_level(None, ...) —
        # None there means "manage_all bypass, always sufficient" (see rules.py),
        # which is a DIFFERENT meaning than "no relationship to this account at
        # all". Guard the no-row case explicitly so the two never collide.
        if manager_row is None or not CloudflareAccountRules.satisfies_level(
            manager_row.access_level, min_level
        ):
            raise InsufficientAccountAccess()
        return AccountAccessGrant(user=user, held_level=manager_row.access_level)

    return check
