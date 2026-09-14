"""Transaction boundary for the cloudflare module."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.uow import AbstractCachedUnitOfWork
from app.core.uow import CachedSqlAlchemyUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    AbstractCloudflareConfigRepository,
    AbstractCloudflareTunnelRepository,
    AbstractDnsRecordRepository,
    AbstractTunnelHostnameRepository,
    CloudflareAccountManagerRepository,
    CloudflareAccountRepository,
    CloudflareConfigRepository,
    CloudflareTunnelRepository,
    DnsRecordRepository,
    TunnelHostnameRepository,
)


class AbstractCloudflareUnitOfWork(AbstractCachedUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    accounts: AbstractCloudflareAccountRepository
    account_managers: AbstractCloudflareAccountManagerRepository
    configs: AbstractCloudflareConfigRepository
    dns_records: AbstractDnsRecordRepository
    tunnels: AbstractCloudflareTunnelRepository
    tunnel_hostnames: AbstractTunnelHostnameRepository


class CloudflareUnitOfWork(AbstractCloudflareUnitOfWork, CachedSqlAlchemyUnitOfWork):
    """Owns the transaction for the cloudflare module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        super().__init__(session, cache)
        self.accounts = CloudflareAccountRepository(session, cache)
        self.account_managers = CloudflareAccountManagerRepository(session)
        self.configs = CloudflareConfigRepository(session)
        self.dns_records = DnsRecordRepository(session)
        self.tunnels = CloudflareTunnelRepository(session)
        self.tunnel_hostnames = TunnelHostnameRepository(session)
