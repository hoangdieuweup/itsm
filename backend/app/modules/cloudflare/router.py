"""HTTP entry points of the cloudflare module. Router thinness (rule #10):
every function below only translates HTTP -> use-case call and wraps the
result in ApiResponse — no formatting/business logic lives here.

Every Layer-2-gated route below ALSO declares its matching Layer-1
require_permission (view for reads, manage for writes) — Layer 2 only
narrows Layer 1, it never grants capability on its own.

PATCH /cloudflare-accounts/{account_id} is the one route whose true Layer-2
requirement is body-dependent (OWNER only when rotating the token). That
decision is made inside UpdateCloudflareAccount's use case, not here —
require_account_access(EDITOR) below is only the floor a static Depends
factory can express; see that use case's own docstring.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.dependencies import (
    get_assign_manager,
    get_create_account,
    get_delete_account,
    get_list_account_managers,
    get_list_visible_accounts,
    get_remove_manager,
    get_reveal_token,
    get_test_connection,
    get_uow,
    get_update_account,
    get_update_manager,
    require_account_access,
)
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.schemas import (
    AccountAccessGrant,
    CloudflareAccountCreate,
    CloudflareAccountManagerAssign,
    CloudflareAccountManagerRead,
    CloudflareAccountManagerUpdate,
    CloudflareAccountRead,
    CloudflareAccountUpdate,
    TokenRevealResponse,
)
from app.modules.cloudflare.services.assign_manager import AssignCloudflareAccountManager
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
from app.modules.cloudflare.services.delete_account import DeleteCloudflareAccount
from app.modules.cloudflare.services.list_account_managers import ListCloudflareAccountManagers
from app.modules.cloudflare.services.list_visible_accounts import ListVisibleCloudflareAccounts
from app.modules.cloudflare.services.remove_manager import RemoveCloudflareAccountManager
from app.modules.cloudflare.services.reveal_token import RevealCloudflareAccountToken
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
from app.modules.cloudflare.services.update_manager import UpdateCloudflareAccountManager
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.rbac.public import require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["cloudflare"])


@router.post("/cloudflare-accounts")
async def create_cloudflare_account(
    body: CloudflareAccountCreate,
    use_case: CreateCloudflareAccount = Depends(get_create_account),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
) -> ApiResponse[CloudflareAccountRead]:
    """Create an account — Cloudflare must confirm the token first; the
    creator is auto-assigned OWNER. No Layer-2 check: the account doesn't
    exist yet to hold a per-account grant on."""
    account = await use_case.execute(
        body.label, body.cf_account_id, body.api_token, actor_id=user.id, actor_email=user.email
    )
    return ApiResponse[CloudflareAccountRead](success=True, data=account)


@router.get("/cloudflare-accounts")
async def list_cloudflare_accounts(
    use_case: ListVisibleCloudflareAccounts = Depends(get_list_visible_accounts),
    _user: UserRead = Depends(require_permission("cloudflare_account", "view")),
) -> ApiResponse[list[CloudflareAccountRead]]:
    """List accounts visible to the current user — filtered server-side, not
    just permission-gated (see ListVisibleCloudflareAccounts)."""
    accounts = await use_case.execute(_user.id)
    return ApiResponse[list[CloudflareAccountRead]](success=True, data=accounts)


@router.get("/cloudflare-accounts/{account_id}")
async def get_cloudflare_account(
    account_id: UUID,
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.VIEWER)),
) -> ApiResponse[CloudflareAccountRead]:
    """Return one account, 404 if it doesn't exist."""
    account = await uow.accounts.get_by_id(account_id)
    if account is None:
        raise CloudflareAccountNotFound()
    return ApiResponse[CloudflareAccountRead](success=True, data=account)


@router.patch("/cloudflare-accounts/{account_id}")
async def update_cloudflare_account(
    account_id: UUID,
    body: CloudflareAccountUpdate,
    use_case: UpdateCloudflareAccount = Depends(get_update_account),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.EDITOR)),
) -> ApiResponse[CloudflareAccountRead]:
    """Rename and/or rotate an account's token. require_account_access(EDITOR)
    above is only the floor — UpdateCloudflareAccount re-checks OWNER itself
    when the body rotates the token."""
    account = await use_case.execute(
        account_id, label=body.label, api_token=body.api_token, grant=grant, actor_email=grant.user.email
    )
    return ApiResponse[CloudflareAccountRead](success=True, data=account)


@router.delete("/cloudflare-accounts/{account_id}")
async def delete_cloudflare_account(
    account_id: UUID,
    use_case: DeleteCloudflareAccount = Depends(get_delete_account),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Delete an account. Its manager rows cascade at the DB level."""
    await use_case.execute(account_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.post("/cloudflare-accounts/{account_id}/test-connection")
async def test_cloudflare_account_connection(
    account_id: UUID,
    use_case: TestCloudflareAccountConnection = Depends(get_test_connection),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Re-verify Cloudflare still accepts the account's stored token."""
    await use_case.execute(account_id)
    return ApiResponse[None](success=True)


@router.post("/cloudflare-accounts/{account_id}/reveal-token")
async def reveal_cloudflare_account_token(
    account_id: UUID,
    use_case: RevealCloudflareAccountToken = Depends(get_reveal_token),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[TokenRevealResponse]:
    """Decrypt and return the account's plaintext token. OWNER only."""
    plaintext = await use_case.execute(account_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[TokenRevealResponse](success=True, data=TokenRevealResponse(api_token=plaintext))


@router.get("/cloudflare-accounts/{account_id}/managers")
async def list_cloudflare_account_managers(
    account_id: UUID,
    use_case: ListCloudflareAccountManagers = Depends(get_list_account_managers),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.VIEWER)),
) -> ApiResponse[list[CloudflareAccountManagerRead]]:
    """List everyone with access to this account."""
    managers = await use_case.execute(account_id)
    return ApiResponse[list[CloudflareAccountManagerRead]](success=True, data=managers)


@router.post("/cloudflare-accounts/{account_id}/managers")
async def assign_cloudflare_account_manager(
    account_id: UUID,
    body: CloudflareAccountManagerAssign,
    use_case: AssignCloudflareAccountManager = Depends(get_assign_manager),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Grant a user access to this account. OWNER only — only an existing
    OWNER (or manage_all) can hand out access to someone else."""
    await use_case.execute(
        account_id, body.user_id, body.access_level, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[None](success=True)


@router.patch("/cloudflare-accounts/{account_id}/managers/{user_id}")
async def update_cloudflare_account_manager(
    account_id: UUID,
    user_id: UUID,
    body: CloudflareAccountManagerUpdate,
    use_case: UpdateCloudflareAccountManager = Depends(get_update_manager),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Change a manager's access_level. Blocked if this would downgrade the
    last OWNER (same effect as removing them)."""
    await use_case.execute(
        account_id, user_id, body.access_level, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[None](success=True)


@router.delete("/cloudflare-accounts/{account_id}/managers/{user_id}")
async def remove_cloudflare_account_manager(
    account_id: UUID,
    user_id: UUID,
    use_case: RemoveCloudflareAccountManager = Depends(get_remove_manager),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Remove a user's access to this account. Blocked if they are the last OWNER."""
    await use_case.execute(account_id, user_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)
