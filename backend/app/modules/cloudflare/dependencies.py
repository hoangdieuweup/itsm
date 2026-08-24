"""FastAPI dependency providers for the cloudflare module. Every provider
depends on an Abstract* contract."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.dependencies import get_cloudflare_client
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.cloudflare.access import resolve_account_access_grant
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound
from app.modules.cloudflare.schemas import AccountAccessGrant
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
from app.modules.cloudflare.services.list_cloudflare_audit_logs import ListCloudflareAuditLogs
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
from app.modules.cloudflare.services.sync_dns_records import SyncDnsRecords
from app.modules.cloudflare.services.sync_tunnels import SyncTunnels
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
from app.modules.cloudflare.services.update_config import UpdateCloudflareConfig
from app.modules.cloudflare.services.update_dns_record import UpdateDnsRecord
from app.modules.cloudflare.services.update_manager import UpdateCloudflareAccountManager
from app.modules.cloudflare.services.update_tunnel_hostname import UpdateTunnelHostname
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork, CloudflareUnitOfWork
from app.modules.projects.public import ProjectsApi, get_projects_api
from app.modules.rbac.public import RbacApi, get_rbac_api
from app.modules.users.public import UsersApi, get_users_api


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> CloudflareUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return CloudflareUnitOfWork(session, cache)


def require_account_access(min_level: AccessLevel):
    """Return a dependency that 403s unless the current user's per-account
    access_level (cloudflare_account_managers) meets min_level, OR they hold
    the cloudflare_account:manage_all Layer-1 permission. account_id is read
    from the path — see require_account_access_for_environment for the
    environment-keyed variant. Returns the resolved AccountAccessGrant rather
    than a bare UserRead — callers that need a stricter, request-body-dependent
    check (UpdateCloudflareAccount's OWNER-for-token-rotation rule) re-validate
    the grant themselves instead of this being expressible as a second static
    Depends factory."""

    async def check(
        account_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    ) -> AccountAccessGrant:
        user = auth_api.current_user()
        return await resolve_account_access_grant(account_id, user, rbac_api, uow, min_level)

    return check


def require_account_access_for_environment(min_level: AccessLevel):
    """Same check as require_account_access, but keyed by environment_id
    (read from the path) instead of account_id — resolves the environment's
    cloudflare_configs row to find which account to check against. Used by
    every DNS/binding route except POST /cloudflare-configs itself, where no
    binding exists yet to resolve from (see CreateCloudflareConfig, which
    calls resolve_account_access_grant directly with the body's account_id —
    account_id is body-only there, and FastAPI cannot resolve a bare-scalar
    sub-dependency parameter from the body, only from the path or query
    string, so no Depends factory can express that check)."""

    async def check(
        environment_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    ) -> AccountAccessGrant:
        user = auth_api.current_user()
        config = await uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        return await resolve_account_access_grant(
            config.cloudflare_account_id, user, rbac_api, uow, min_level
        )

    return check


async def get_create_account(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateCloudflareAccount:
    """Provide the create-account use case."""
    return CreateCloudflareAccount(uow, client, audit_api)


async def get_update_account(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateCloudflareAccount:
    """Provide the update-account use case."""
    return UpdateCloudflareAccount(uow, client, audit_api)


async def get_delete_account(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> DeleteCloudflareAccount:
    """Provide the delete-account use case."""
    return DeleteCloudflareAccount(uow, audit_api)


async def get_test_connection(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
) -> TestCloudflareAccountConnection:
    """Provide the test-connection use case."""
    return TestCloudflareAccountConnection(uow, client)


async def get_reveal_token(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> RevealCloudflareAccountToken:
    """Provide the reveal-token use case."""
    return RevealCloudflareAccountToken(uow, audit_api)


async def get_list_visible_accounts(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), rbac_api: RbacApi = Depends(get_rbac_api)
) -> ListVisibleCloudflareAccounts:
    """Provide the list-visible-accounts use case."""
    return ListVisibleCloudflareAccounts(uow, rbac_api)


async def get_list_account_managers(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), users_api: UsersApi = Depends(get_users_api)
) -> ListCloudflareAccountManagers:
    """Provide the list-account-managers use case."""
    return ListCloudflareAccountManagers(uow, users_api)


async def get_assign_manager(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> AssignCloudflareAccountManager:
    """Provide the assign-manager use case."""
    return AssignCloudflareAccountManager(uow, audit_api)


async def get_update_manager(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> UpdateCloudflareAccountManager:
    """Provide the update-manager use case."""
    return UpdateCloudflareAccountManager(uow, audit_api)


async def get_remove_manager(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> RemoveCloudflareAccountManager:
    """Provide the remove-manager use case."""
    return RemoveCloudflareAccountManager(uow, audit_api)


async def get_create_config(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    rbac_api: RbacApi = Depends(get_rbac_api),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateCloudflareConfig:
    """Provide the create-config use case."""
    return CreateCloudflareConfig(uow, client, rbac_api, projects_api, audit_api)


async def get_update_config(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateCloudflareConfig:
    """Provide the update-config use case."""
    return UpdateCloudflareConfig(uow, client, audit_api)


async def get_delete_config(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> DeleteCloudflareConfig:
    """Provide the delete-config use case."""
    return DeleteCloudflareConfig(uow, audit_api)


async def get_list_zones(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
) -> ListZones:
    """Provide the list-zones use case."""
    return ListZones(uow, client)


async def get_list_cloudflare_audit_logs(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
) -> ListCloudflareAuditLogs:
    """Provide the list-audit-logs use case."""
    return ListCloudflareAuditLogs(uow, client)


async def get_list_dns_records(uow: AbstractCloudflareUnitOfWork = Depends(get_uow)) -> ListDnsRecords:
    """Provide the list-dns-records use case."""
    return ListDnsRecords(uow)


async def get_sync_dns_records(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    projects_api: ProjectsApi = Depends(get_projects_api),
) -> SyncDnsRecords:
    """Provide the sync-dns-records use case."""
    return SyncDnsRecords(uow, client, projects_api)


async def get_create_dns_record(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateDnsRecord:
    """Provide the create-dns-record use case."""
    return CreateDnsRecord(uow, client, audit_api)


async def get_update_dns_record(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateDnsRecord:
    """Provide the update-dns-record use case."""
    return UpdateDnsRecord(uow, client, audit_api)


async def get_delete_dns_record(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteDnsRecord:
    """Provide the delete-dns-record use case."""
    return DeleteDnsRecord(uow, client, audit_api)


async def get_create_tunnel(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateCloudflareTunnel:
    """Provide the create-tunnel use case."""
    return CreateCloudflareTunnel(uow, client, audit_api)


async def get_delete_tunnel(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteCloudflareTunnel:
    """Provide the delete-tunnel use case."""
    return DeleteCloudflareTunnel(uow, client, audit_api)


async def get_reveal_tunnel_token(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> RevealCloudflareTunnelToken:
    """Provide the reveal-tunnel-token use case."""
    return RevealCloudflareTunnelToken(uow, client, audit_api)


async def get_refresh_tunnel_status(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
) -> RefreshTunnelStatus:
    """Provide the refresh-tunnel-status use case."""
    return RefreshTunnelStatus(uow, client)


async def get_list_tunnels(uow: AbstractCloudflareUnitOfWork = Depends(get_uow)) -> ListTunnels:
    """Provide the list-tunnels use case."""
    return ListTunnels(uow)


async def get_sync_tunnels(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    projects_api: ProjectsApi = Depends(get_projects_api),
) -> SyncTunnels:
    """Provide the sync-tunnels use case."""
    return SyncTunnels(uow, client, projects_api)


async def get_list_tunnel_hostnames(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
) -> ListTunnelHostnames:
    """Provide the list-tunnel-hostnames use case."""
    return ListTunnelHostnames(uow)


async def get_add_tunnel_hostname(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    cache: CacheClient = Depends(get_cache),
    audit_api: AuditApi = Depends(get_audit_api),
) -> AddTunnelHostname:
    """Provide the add-tunnel-hostname use case."""
    return AddTunnelHostname(uow, client, cache, audit_api)


async def get_update_tunnel_hostname(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    cache: CacheClient = Depends(get_cache),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateTunnelHostname:
    """Provide the update-tunnel-hostname use case."""
    return UpdateTunnelHostname(uow, client, cache, audit_api)


async def get_remove_tunnel_hostname(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    cache: CacheClient = Depends(get_cache),
    audit_api: AuditApi = Depends(get_audit_api),
) -> RemoveTunnelHostname:
    """Provide the remove-tunnel-hostname use case."""
    return RemoveTunnelHostname(uow, client, cache, audit_api)
