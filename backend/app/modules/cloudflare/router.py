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
from app.integrations.cloudflare.schemas import ZoneOption
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.dependencies import (
    get_add_tunnel_hostname,
    get_assign_manager,
    get_create_account,
    get_create_config,
    get_create_dns_record,
    get_create_tunnel,
    get_delete_account,
    get_delete_config,
    get_delete_dns_record,
    get_delete_tunnel,
    get_list_account_managers,
    get_list_dns_records,
    get_list_tunnel_hostnames,
    get_list_tunnels,
    get_list_visible_accounts,
    get_list_zones,
    get_refresh_tunnel_status,
    get_remove_manager,
    get_remove_tunnel_hostname,
    get_reveal_token,
    get_reveal_tunnel_token,
    get_test_connection,
    get_uow,
    get_update_account,
    get_update_config,
    get_update_dns_record,
    get_update_manager,
    get_update_tunnel_hostname,
    require_account_access,
    require_account_access_for_environment,
)
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound, CloudflareConfigNotFound
from app.modules.cloudflare.schemas import (
    AccountAccessGrant,
    CloudflareAccountCreate,
    CloudflareAccountManagerAssign,
    CloudflareAccountManagerRead,
    CloudflareAccountManagerUpdate,
    CloudflareAccountRead,
    CloudflareAccountUpdate,
    CloudflareConfigCreate,
    CloudflareConfigRead,
    CloudflareConfigUpdate,
    CloudflareTunnelCreate,
    CloudflareTunnelCreateResponse,
    CloudflareTunnelRead,
    DnsRecordCreate,
    DnsRecordRead,
    DnsRecordUpdate,
    TokenRevealResponse,
    TunnelPublicHostnameCreate,
    TunnelPublicHostnameRead,
    TunnelPublicHostnameUpdate,
    TunnelTokenResponse,
)
from app.modules.cloudflare.services.add_tunnel_hostname import AddTunnelHostname
from app.modules.cloudflare.services.assign_manager import AssignCloudflareAccountManager
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
from app.modules.cloudflare.services.create_config import CreateCloudflareConfig
from app.modules.cloudflare.services.create_dns_record import CreateDnsRecord
from app.modules.cloudflare.services.create_tunnel import CreateCloudflareTunnel
from app.modules.cloudflare.services.delete_account import DeleteCloudflareAccount
from app.modules.cloudflare.services.delete_config import DeleteCloudflareConfig
from app.modules.cloudflare.services.delete_dns_record import DeleteDnsRecord
from app.modules.cloudflare.services.delete_tunnel import DeleteCloudflareTunnel
from app.modules.cloudflare.services.list_account_managers import ListCloudflareAccountManagers
from app.modules.cloudflare.services.list_dns_records import ListDnsRecords
from app.modules.cloudflare.services.list_tunnel_hostnames import ListTunnelHostnames
from app.modules.cloudflare.services.list_tunnels import ListTunnels
from app.modules.cloudflare.services.list_visible_accounts import ListVisibleCloudflareAccounts
from app.modules.cloudflare.services.list_zones import ListZones
from app.modules.cloudflare.services.refresh_tunnel_status import RefreshTunnelStatus
from app.modules.cloudflare.services.remove_manager import RemoveCloudflareAccountManager
from app.modules.cloudflare.services.remove_tunnel_hostname import RemoveTunnelHostname
from app.modules.cloudflare.services.reveal_token import RevealCloudflareAccountToken
from app.modules.cloudflare.services.reveal_tunnel_token import RevealCloudflareTunnelToken
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
from app.modules.cloudflare.services.update_config import UpdateCloudflareConfig
from app.modules.cloudflare.services.update_dns_record import UpdateDnsRecord
from app.modules.cloudflare.services.update_manager import UpdateCloudflareAccountManager
from app.modules.cloudflare.services.update_tunnel_hostname import UpdateTunnelHostname
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.rbac.public import RbacActions, RbacResources, require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["cloudflare"])


@router.post("/cloudflare-accounts")
async def create_cloudflare_account(
    body: CloudflareAccountCreate,
    use_case: CreateCloudflareAccount = Depends(get_create_account),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
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
    _user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
) -> ApiResponse[list[CloudflareAccountRead]]:
    """List accounts visible to the current user — filtered server-side, not
    just permission-gated (see ListVisibleCloudflareAccounts)."""
    accounts = await use_case.execute(_user.id)
    return ApiResponse[list[CloudflareAccountRead]](success=True, data=accounts)


@router.get("/cloudflare-accounts/{account_id}")
async def get_cloudflare_account(
    account_id: UUID,
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
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
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
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
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Delete an account. Its manager rows cascade at the DB level."""
    await use_case.execute(account_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.post("/cloudflare-accounts/{account_id}/test-connection")
async def test_cloudflare_account_connection(
    account_id: UUID,
    use_case: TestCloudflareAccountConnection = Depends(get_test_connection),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Re-verify Cloudflare still accepts the account's stored token."""
    await use_case.execute(account_id)
    return ApiResponse[None](success=True)


@router.post("/cloudflare-accounts/{account_id}/reveal-token")
async def reveal_cloudflare_account_token(
    account_id: UUID,
    use_case: RevealCloudflareAccountToken = Depends(get_reveal_token),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[TokenRevealResponse]:
    """Decrypt and return the account's plaintext token. OWNER only."""
    plaintext = await use_case.execute(account_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[TokenRevealResponse](success=True, data=TokenRevealResponse(api_token=plaintext))


@router.get("/cloudflare-accounts/{account_id}/managers")
async def list_cloudflare_account_managers(
    account_id: UUID,
    use_case: ListCloudflareAccountManagers = Depends(get_list_account_managers),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
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
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
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
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
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
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Remove a user's access to this account. Blocked if they are the last OWNER."""
    await use_case.execute(account_id, user_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.get("/cloudflare-accounts/{account_id}/zones")
async def list_zones(
    account_id: UUID,
    use_case: ListZones = Depends(get_list_zones),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.VIEWER)),
) -> ApiResponse[list[ZoneOption]]:
    """List zones available on an account, for the bind-time zone picker."""
    zones = await use_case.execute(account_id)
    return ApiResponse[list[ZoneOption]](success=True, data=zones)


@router.post("/cloudflare-configs")
async def create_cloudflare_config(
    body: CloudflareConfigCreate,
    use_case: CreateCloudflareConfig = Depends(get_create_config),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
) -> ApiResponse[CloudflareConfigRead]:
    """Bind an environment to an account + zone. No Depends(require_account_access(...))
    here — cloudflare_account_id is body-only (Decision #1); CreateCloudflareConfig
    resolves the Layer-2 grant itself via resolve_account_access_grant."""
    config = await use_case.execute(body.environment_id, body.cloudflare_account_id, body.zone_id, actor=user)
    return ApiResponse[CloudflareConfigRead](success=True, data=config)


@router.get("/environments/{environment_id}/cloudflare-config")
async def get_cloudflare_config(
    environment_id: UUID,
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[CloudflareConfigRead]:
    """Return one environment's binding, 404 if unbound."""
    config = await uow.configs.get_by_environment_id(environment_id)
    if config is None:
        raise CloudflareConfigNotFound()
    return ApiResponse[CloudflareConfigRead](success=True, data=config)


@router.patch("/environments/{environment_id}/cloudflare-config")
async def update_cloudflare_config(
    environment_id: UUID,
    body: CloudflareConfigUpdate,
    use_case: UpdateCloudflareConfig = Depends(get_update_config),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[CloudflareConfigRead]:
    """Rebind an environment to a different zone on the same account."""
    config = await use_case.execute(
        environment_id, body.zone_id, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[CloudflareConfigRead](success=True, data=config)


@router.delete("/environments/{environment_id}/cloudflare-config")
async def delete_cloudflare_config(
    environment_id: UUID,
    use_case: DeleteCloudflareConfig = Depends(get_delete_config),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Remove an environment's binding. Blocked while DNS records still exist."""
    await use_case.execute(environment_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.get("/environments/{environment_id}/dns-records")
async def list_environment_dns_records(
    environment_id: UUID,
    use_case: ListDnsRecords = Depends(get_list_dns_records),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[list[DnsRecordRead]]:
    """List an environment's DNS records."""
    records = await use_case.execute(environment_id)
    return ApiResponse[list[DnsRecordRead]](success=True, data=records)


@router.post("/environments/{environment_id}/dns-records")
async def create_environment_dns_record(
    environment_id: UUID,
    body: DnsRecordCreate,
    use_case: CreateDnsRecord = Depends(get_create_dns_record),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[DnsRecordRead]:
    """Create a DNS record — Cloudflare must confirm first (Decision #3)."""
    record = await use_case.execute(
        environment_id,
        body.record_type,
        body.name,
        body.content,
        body.priority,
        body.proxied,
        body.ttl,
        actor=user,
    )
    return ApiResponse[DnsRecordRead](success=True, data=record)


@router.patch("/environments/{environment_id}/dns-records/{record_id}")
async def update_environment_dns_record(
    environment_id: UUID,
    record_id: UUID,
    body: DnsRecordUpdate,
    use_case: UpdateDnsRecord = Depends(get_update_dns_record),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[DnsRecordRead]:
    """Update a DNS record — Cloudflare must confirm first (Decision #3)."""
    record = await use_case.execute(
        environment_id, record_id, body.content, body.priority, body.proxied, body.ttl, actor=user
    )
    return ApiResponse[DnsRecordRead](success=True, data=record)


@router.delete("/environments/{environment_id}/dns-records/{record_id}")
async def delete_environment_dns_record(
    environment_id: UUID,
    record_id: UUID,
    use_case: DeleteDnsRecord = Depends(get_delete_dns_record),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Delete a DNS record — Cloudflare must confirm first (Decision #3)."""
    await use_case.execute(environment_id, record_id, actor=user)
    return ApiResponse[None](success=True)


@router.get("/environments/{environment_id}/cloudflare-tunnels")
async def list_environment_tunnels(
    environment_id: UUID,
    use_case: ListTunnels = Depends(get_list_tunnels),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[list[CloudflareTunnelRead]]:
    """List every tunnel bound to an environment (1:N)."""
    tunnels = await use_case.execute(environment_id)
    return ApiResponse[list[CloudflareTunnelRead]](success=True, data=tunnels)


@router.post("/environments/{environment_id}/cloudflare-tunnels")
async def create_environment_tunnel(
    environment_id: UUID,
    body: CloudflareTunnelCreate,
    use_case: CreateCloudflareTunnel = Depends(get_create_tunnel),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[CloudflareTunnelCreateResponse]:
    """Create a tunnel and return its one-time connector token (Decision #8)."""
    tunnel, token = await use_case.execute(environment_id, body.name, actor=user)
    return ApiResponse[CloudflareTunnelCreateResponse](
        success=True, data=CloudflareTunnelCreateResponse(tunnel=tunnel, token=token)
    )


@router.delete("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}")
async def delete_environment_tunnel(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: DeleteCloudflareTunnel = Depends(get_delete_tunnel),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Delete a tunnel. Its public hostnames cascade at the DB level (Decision #7)."""
    await use_case.execute(environment_id, tunnel_id, actor=user)
    return ApiResponse[None](success=True)


@router.post("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/reveal-token")
async def reveal_environment_tunnel_token(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: RevealCloudflareTunnelToken = Depends(get_reveal_tunnel_token),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[TunnelTokenResponse]:
    """Re-fetch the connector token live. EDITOR only (Decision #6 — a
    narrower blast radius than an account's own OWNER-gated reveal-token)."""
    token = await use_case.execute(environment_id, tunnel_id, actor=user)
    return ApiResponse[TunnelTokenResponse](success=True, data=TunnelTokenResponse(token=token))


@router.post("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/refresh-status")
async def refresh_environment_tunnel_status(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: RefreshTunnelStatus = Depends(get_refresh_tunnel_status),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[CloudflareTunnelRead]:
    """On-demand status sync (Decision #10 — never automatic)."""
    tunnel = await use_case.execute(environment_id, tunnel_id)
    return ApiResponse[CloudflareTunnelRead](success=True, data=tunnel)


@router.get("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames")
async def list_environment_tunnel_hostnames(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: ListTunnelHostnames = Depends(get_list_tunnel_hostnames),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[list[TunnelPublicHostnameRead]]:
    """List every public hostname published through a tunnel."""
    hostnames = await use_case.execute(environment_id, tunnel_id)
    return ApiResponse[list[TunnelPublicHostnameRead]](success=True, data=hostnames)


@router.post("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames")
async def add_environment_tunnel_hostname(
    environment_id: UUID,
    tunnel_id: UUID,
    body: TunnelPublicHostnameCreate,
    use_case: AddTunnelHostname = Depends(get_add_tunnel_hostname),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[TunnelPublicHostnameRead]:
    """Add a hostname — Redis-locked GET-modify-PUT (Decisions #1-#5). 409 if
    another edit is already in flight for this tunnel."""
    hostname = await use_case.execute(environment_id, tunnel_id, body.hostname, body.service, actor=user)
    return ApiResponse[TunnelPublicHostnameRead](success=True, data=hostname)


@router.patch("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames/{hostname_id}")
async def update_environment_tunnel_hostname(
    environment_id: UUID,
    tunnel_id: UUID,
    hostname_id: UUID,
    body: TunnelPublicHostnameUpdate,
    use_case: UpdateTunnelHostname = Depends(get_update_tunnel_hostname),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[TunnelPublicHostnameRead]:
    """Update a hostname's service target — same Redis-locked shape."""
    hostname = await use_case.execute(environment_id, tunnel_id, hostname_id, body.service, actor=user)
    return ApiResponse[TunnelPublicHostnameRead](success=True, data=hostname)


@router.delete("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames/{hostname_id}")
async def remove_environment_tunnel_hostname(
    environment_id: UUID,
    tunnel_id: UUID,
    hostname_id: UUID,
    use_case: RemoveTunnelHostname = Depends(get_remove_tunnel_hostname),
    user: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Remove a hostname — same Redis-locked shape."""
    await use_case.execute(environment_id, tunnel_id, hostname_id, actor=user)
    return ApiResponse[None](success=True)
