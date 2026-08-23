"""Shared Layer-2 access-resolution logic. Lives in its own module — NOT
dependencies.py — so both dependencies.py's require_account_access* factory
closures AND a service that needs to resolve a grant directly (see
CreateCloudflareConfig: cloudflare_account_id is body-only, no Depends
factory can read it at decoration time) can import this without a cycle.
dependencies.py already imports service classes to build its provider
functions, so a service can never import dependencies.py back."""

from uuid import UUID

from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.exceptions import InsufficientAccountAccess
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.schemas import AccountAccessGrant
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.rbac.public import RbacApi
from app.modules.users.public import UserRead


async def resolve_account_access_grant(
    account_id: UUID,
    user: UserRead,
    rbac_api: RbacApi,
    uow: AbstractCloudflareUnitOfWork,
    min_level: AccessLevel,
) -> AccountAccessGrant:
    """Return the caller's AccountAccessGrant for account_id, or raise
    InsufficientAccountAccess. manage_all bypasses with held_level=None
    (CloudflareAccountRules.satisfies_level treats None as always-sufficient)."""
    if await rbac_api.has_permission(user.id, "cloudflare_account", "manage_all"):
        return AccountAccessGrant(user=user, held_level=None)

    manager_row = await uow.account_managers.get_for_user(account_id, user.id)
    if manager_row is None or not CloudflareAccountRules.satisfies_level(manager_row.access_level, min_level):
        raise InsufficientAccountAccess()
    return AccountAccessGrant(user=user, held_level=manager_row.access_level)
