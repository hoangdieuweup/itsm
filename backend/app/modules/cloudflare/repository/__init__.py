"""Single access path to the cloudflare module's tables, one file per aggregate. Every class
is re-exported here so callers keep importing from app.modules.cloudflare.repository."""

from app.modules.cloudflare.repository.account_managers import (
    AbstractCloudflareAccountManagerRepository,
    CloudflareAccountManagerRepository,
    CloudflareAccountManagerRow,
)
from app.modules.cloudflare.repository.accounts import (
    AbstractCloudflareAccountRepository,
    CloudflareAccountRepository,
)
from app.modules.cloudflare.repository.configs import (
    AbstractCloudflareConfigRepository,
    CloudflareConfigRepository,
)
from app.modules.cloudflare.repository.dns_records import (
    AbstractDnsRecordRepository,
    DnsRecordRepository,
)
from app.modules.cloudflare.repository.tunnel_hostnames import (
    AbstractTunnelHostnameRepository,
    TunnelHostnameRepository,
)
from app.modules.cloudflare.repository.tunnels import (
    AbstractCloudflareTunnelRepository,
    CloudflareTunnelRepository,
)

__all__ = [
    "AbstractCloudflareAccountManagerRepository",
    "AbstractCloudflareAccountRepository",
    "AbstractCloudflareConfigRepository",
    "AbstractCloudflareTunnelRepository",
    "AbstractDnsRecordRepository",
    "AbstractTunnelHostnameRepository",
    "CloudflareAccountManagerRepository",
    "CloudflareAccountManagerRow",
    "CloudflareAccountRepository",
    "CloudflareConfigRepository",
    "CloudflareTunnelRepository",
    "DnsRecordRepository",
    "TunnelHostnameRepository",
]
