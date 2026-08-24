"""Schemas for the cloudflare module."""

from datetime import datetime
from uuid import UUID

from app.core.models import CustomModel, FrozenModel
from app.modules.cloudflare.constants import AccessLevel, DnsRecordType, ManagedBy, TunnelStatus
from app.modules.users.public import UserRead


class CloudflareAccountRead(FrozenModel):
    """Representation safe to round trip through the cache. Never includes api_token."""

    id: UUID
    label: str
    cf_account_id: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class CloudflareAccountCreate(CustomModel):
    """Request body for POST /cloudflare-accounts."""

    label: str
    cf_account_id: str
    api_token: str


class CloudflareAccountUpdate(CustomModel):
    """Request body for PATCH /cloudflare-accounts/{id}. None means unchanged.
    Providing api_token means "rotate the token" and requires OWNER — see
    UpdateCloudflareAccount's use case."""

    label: str | None = None
    api_token: str | None = None


class CloudflareAccountManagerRead(FrozenModel):
    """One manager row, enriched with the target user's email/name (resolved
    via UsersApi in the service layer — the repository only knows user_id)."""

    user_id: UUID
    email: str
    name: str
    access_level: AccessLevel
    created_at: datetime


class CloudflareAccountManagerAssign(CustomModel):
    """Request body for POST /cloudflare-accounts/{id}/managers."""

    user_id: UUID
    access_level: AccessLevel


class CloudflareAccountManagerUpdate(CustomModel):
    """Request body for PATCH /cloudflare-accounts/{id}/managers/{user_id}."""

    access_level: AccessLevel


class TokenRevealResponse(FrozenModel):
    """Response body for POST /cloudflare-accounts/{id}/reveal-token. Never cached."""

    api_token: str


class AccountAccessGrant(FrozenModel):
    """The resolved outcome of a Layer-2 require_account_access check: which
    user, and at what access_level — None means they passed via the
    cloudflare_account:manage_all Layer-1 bypass, which
    CloudflareAccountRules.satisfies_level treats as always-sufficient.

    Lives here (not in dependencies.py, where it's constructed) so both
    dependencies.py AND services/update_account.py can import it without a
    cycle — dependencies.py imports service classes to build its provider
    functions, so a service can never import dependencies.py back."""

    user: UserRead
    held_level: AccessLevel | None


class CloudflareConfigRead(FrozenModel):
    """One environment's Cloudflare binding."""

    id: UUID
    environment_id: UUID
    cloudflare_account_id: UUID
    zone_id: str
    zone_name: str
    created_at: datetime
    updated_at: datetime


class CloudflareConfigCreate(CustomModel):
    """Request body for POST /cloudflare-configs."""

    environment_id: UUID
    cloudflare_account_id: UUID
    zone_id: str


class CloudflareConfigUpdate(CustomModel):
    """Request body for PATCH /environments/{id}/cloudflare-config. Only the
    zone can change — moving to a different account entirely is delete+recreate."""

    zone_id: str


class DnsRecordRead(FrozenModel):
    """One DNS record."""

    id: UUID
    environment_id: UUID
    cf_record_id: str
    record_type: DnsRecordType
    name: str
    content: str
    priority: int | None = None
    proxied: bool
    ttl: int
    managed_by: ManagedBy
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DnsRecordCreate(CustomModel):
    """Request body for POST /environments/{id}/dns-records. priority is
    required only for MX — see CloudflareDnsRules.normalize_priority."""

    record_type: DnsRecordType
    name: str
    content: str
    priority: int | None = None
    proxied: bool = False
    ttl: int = 1


class DnsRecordUpdate(CustomModel):
    """Request body for PATCH .../dns-records/{id}. record_type is immutable
    after creation — changing type means delete+recreate."""

    content: str
    priority: int | None = None
    proxied: bool = False
    ttl: int = 1


class CloudflareTunnelRead(FrozenModel):
    """One Cloudflare Tunnel, account-scoped — see the model docstring."""

    id: UUID
    cloudflare_account_id: UUID
    cf_tunnel_id: str
    name: str
    status: TunnelStatus
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CloudflareTunnelCreate(CustomModel):
    """Request body for POST .../cloudflare-tunnels. No config_src field —
    it's hardcoded to "cloudflare" inside the client (Decision #9)."""

    name: str


class TunnelTokenResponse(FrozenModel):
    """Response body for the create and reveal-token endpoints. Never cached
    or persisted anywhere (Decision #8)."""

    token: str


class CloudflareTunnelCreateResponse(FrozenModel):
    """Response body for POST .../cloudflare-tunnels — bundles the created
    tunnel with its one-time connector token (Decision #8: never persisted,
    shown exactly once here and again only via the reveal-token endpoint)."""

    tunnel: CloudflareTunnelRead
    token: str


class TunnelPublicHostnameRead(FrozenModel):
    """One public hostname published through a Tunnel. environment_id is
    None when the hostname didn't match any bound environment's base_url
    (see TunnelHostnameRules.match_environment_id)."""

    id: UUID
    tunnel_id: UUID
    environment_id: UUID | None = None
    hostname: str
    service: str
    managed_by: ManagedBy
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TunnelPublicHostnameCreate(CustomModel):
    """Request body for POST .../hostnames."""

    hostname: str
    service: str


class TunnelPublicHostnameUpdate(CustomModel):
    """Request body for PATCH .../hostnames/{id}. hostname is immutable —
    changing it means delete+recreate, mirrors DnsRecordUpdate's record_type
    immutability."""

    service: str
