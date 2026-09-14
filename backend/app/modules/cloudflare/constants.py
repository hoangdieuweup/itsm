"""Constants and enums owned by the cloudflare module."""

from enum import StrEnum


class CloudflareAccountLimits:
    """Numeric limits owned by the cloudflare module."""

    MAX_LABEL_LENGTH = 255
    MAX_CF_ACCOUNT_ID_LENGTH = 64


class AccessLevel(StrEnum):
    """Per-account access level, ranked VIEWER < EDITOR < OWNER. See AccessLevelRanking.RANK."""

    VIEWER = "viewer"
    EDITOR = "editor"
    OWNER = "owner"


class AccessLevelRanking:
    """Numeric rank per AccessLevel, owned by the cloudflare module. Used by
    CloudflareAccountRules.satisfies_level for >= comparisons."""

    RANK: dict[AccessLevel, int] = {
        AccessLevel.VIEWER: 0,
        AccessLevel.EDITOR: 1,
        AccessLevel.OWNER: 2,
    }


class CloudflareAccountsCacheKeys:
    """Cache identity owned by the cloudflare module. See references/caching.md."""

    ACCOUNT_ENTITY = "cloudflare_account"
    TTL_SECONDS = 300


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    ACCOUNT_NOT_FOUND = "cloudflare_account_not_found"
    ACCOUNT_TOKEN_UNREADABLE = "cloudflare_account_token_unreadable"
    WEBHOOK_SECRET_UNREADABLE = "cloudflare_webhook_secret_unreadable"
    MANAGER_NOT_FOUND = "cloudflare_account_manager_not_found"
    INSUFFICIENT_ACCESS = "cloudflare_insufficient_account_access"
    LAST_OWNER_REMOVAL_BLOCKED = "cloudflare_last_owner_removal_blocked"
    CONFIG_NOT_FOUND = "cloudflare_config_not_found"
    CONFIG_ALREADY_EXISTS = "cloudflare_config_already_exists"
    ENVIRONMENT_NOT_FOUND = "cloudflare_environment_not_found"
    DNS_RECORD_NOT_FOUND = "cloudflare_dns_record_not_found"
    ZONE_NOT_OWNED_BY_ACCOUNT = "cloudflare_zone_not_owned_by_account"
    MISSING_DNS_PRIORITY = "cloudflare_missing_dns_priority"
    DNS_SYNC_FAILED = "cloudflare_dns_sync_failed"
    DNS_RECORDS_EXIST_FOR_CONFIG = "cloudflare_dns_records_exist_for_config"
    TUNNEL_NOT_FOUND = "cloudflare_tunnel_not_found"
    TUNNEL_HOSTNAME_NOT_FOUND = "cloudflare_tunnel_hostname_not_found"
    TUNNEL_CONFIG_LOCKED = "cloudflare_tunnel_config_locked"
    TUNNEL_HOSTNAME_ALREADY_EXISTS = "cloudflare_tunnel_hostname_already_exists"
    TUNNEL_INGRESS_SYNC_FAILED = "cloudflare_tunnel_ingress_sync_failed"
    TUNNEL_HOSTNAME_DOMAIN_MISMATCH = "cloudflare_tunnel_hostname_domain_mismatch"
    TUNNEL_HOSTNAME_ENVIRONMENT_MISMATCH = "cloudflare_tunnel_hostname_environment_mismatch"
    ENVIRONMENT_BASE_URL_NOT_CONFIGURED = "cloudflare_environment_base_url_not_configured"


class CloudflareAccountAuditActions(StrEnum):
    """Action identifiers this module writes via audit.log_event. Centralized
    so the same string is never typo'd or drifted across call sites — audit
    itself is domain-agnostic and only ever sees whatever string is passed."""

    ACCOUNT_CREATED = "CLOUDFLARE_ACCOUNT_CREATED"
    ACCOUNT_UPDATED = "CLOUDFLARE_ACCOUNT_UPDATED"
    ACCOUNT_DELETED = "CLOUDFLARE_ACCOUNT_DELETED"
    TOKEN_REVEALED = "CLOUDFLARE_ACCOUNT_TOKEN_REVEALED"
    MANAGER_ASSIGNED = "CLOUDFLARE_ACCOUNT_MANAGER_ASSIGNED"
    MANAGER_UPDATED = "CLOUDFLARE_ACCOUNT_MANAGER_UPDATED"
    MANAGER_REMOVED = "CLOUDFLARE_ACCOUNT_MANAGER_REMOVED"


class DnsRecordType(StrEnum):
    """Cloudflare DNS record type this module manages."""

    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    TXT = "TXT"
    MX = "MX"
    OTHER = "OTHER"


class LogSource(StrEnum):
    """Where Phase 6's log viewer reads this environment's Cloudflare logs
    from. Unused until Phase 6 — column exists now per the schema doc's own
    table shape, additive not restructured."""

    AUDIT_LOG = "audit_log"
    LOGPUSH = "logpush"
    GRAPHQL_ANALYTICS = "graphql_analytics"


class ManagedBy(StrEnum):
    """Whether a dns_records row was created through this app (SYSTEM) or
    discovered on Cloudflare without a matching local row (EXTERNAL — set by
    Phase 10's reconciliation job, not written by anything in this phase)."""

    SYSTEM = "system"
    EXTERNAL = "external"


class CloudflareDnsAuditActions(StrEnum):
    """Action identifiers this phase writes via audit.log_event. Kept
    separate from CloudflareAccountAuditActions — different aggregate."""

    CONFIG_CREATED = "CLOUDFLARE_CONFIG_CREATED"
    CONFIG_UPDATED = "CLOUDFLARE_CONFIG_UPDATED"
    CONFIG_DELETED = "CLOUDFLARE_CONFIG_DELETED"
    DNS_RECORD_CREATED = "CLOUDFLARE_DNS_RECORD_CREATED"
    DNS_RECORD_UPDATED = "CLOUDFLARE_DNS_RECORD_UPDATED"
    DNS_RECORD_DELETED = "CLOUDFLARE_DNS_RECORD_DELETED"


class TunnelStatus(StrEnum):
    """Connection health of a Cloudflare Tunnel, synced on demand from
    GET .../connections (Decision #10) — DEGRADED is never auto-set, no
    documented threshold exists for it."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class CloudflareTunnelAuditActions(StrEnum):
    """Action identifiers this phase writes via audit.log_event."""

    TUNNEL_CREATED = "CLOUDFLARE_TUNNEL_CREATED"
    TUNNEL_DELETED = "CLOUDFLARE_TUNNEL_DELETED"
    TUNNEL_TOKEN_REVEALED = "CLOUDFLARE_TUNNEL_TOKEN_REVEALED"
    TUNNEL_HOSTNAME_CREATED = "CLOUDFLARE_TUNNEL_HOSTNAME_CREATED"
    TUNNEL_HOSTNAME_UPDATED = "CLOUDFLARE_TUNNEL_HOSTNAME_UPDATED"
    TUNNEL_HOSTNAME_DELETED = "CLOUDFLARE_TUNNEL_HOSTNAME_DELETED"


class CloudflareTunnelLockDefaults:
    """Lock TTL for the 3 hostname-mutation services — matches the master
    plan's `SET lock:tunnel:<id> NX PX 5000` (5 seconds)."""

    INGRESS_LOCK_TTL_SECONDS = 5


class DriftKind(StrEnum):
    """What kind of drift a reconciled DNS record / tunnel hostname
    represents, relative to the last known local state."""

    NEW_EXTERNAL = "new_external"
    VANISHED = "vanished"


class CloudflareWebhookDefaults:
    """Fixed values used when registering this app's webhook destination
    with a Cloudflare account (Decision #5, Phase 9)."""

    DESTINATION_NAME = "itsm-alerting"
