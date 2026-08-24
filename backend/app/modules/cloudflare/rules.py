"""Business rules for the cloudflare module.

Everything here is a pure decision: no I/O, no framework, no database.
"""

from urllib.parse import urlparse
from uuid import UUID

from app.core.base.markers import rule
from app.modules.cloudflare.constants import AccessLevel, AccessLevelRanking, DnsRecordType, TunnelStatus
from app.modules.cloudflare.exceptions import MissingDnsRecordPriority
from app.modules.cloudflare.schemas import CloudflareTunnelRead


class CloudflareAccountRules:
    """Every business decision about a cloudflare account or its per-account ACL."""

    @staticmethod
    @rule
    def satisfies_level(held: AccessLevel | None, required: AccessLevel) -> bool:
        """True if held meets or exceeds required. held=None means the caller
        passed the check via the manage_all Layer-1 bypass — always satisfies,
        since manage_all is a strictly higher grant than any per-account row."""
        if held is None:
            return True
        return AccessLevelRanking.RANK[held] >= AccessLevelRanking.RANK[required]

    @staticmethod
    @rule
    def required_level_for_update(rotates_token: bool) -> AccessLevel:
        """Rotating the token is equivalent to re-proving ownership of the
        credential, so it needs OWNER. Any other field-only edit needs EDITOR."""
        return AccessLevel.OWNER if rotates_token else AccessLevel.EDITOR

    @staticmethod
    @rule
    def blocks_last_owner_removal(access_level: AccessLevel, remaining_owner_grants: int) -> bool:
        """True when removing or downgrading this grant would leave zero
        OWNERs able to manage the account. remaining_owner_grants counts
        OWNER-level rows *including* the one about to be changed — mirrors
        RbacRules.blocks_last_admin_removal's exact convention. Applies
        unconditionally: manage_all holders get no exemption, since exempting
        them would let a superuser strip the last OWNER and permanently
        escalate routine account admin into a superuser-only workflow."""
        return access_level == AccessLevel.OWNER and remaining_owner_grants <= 1


class CloudflareDnsRules:
    """Pure decision rules for DNS record validation. No I/O."""

    @staticmethod
    @rule
    def requires_priority(record_type: DnsRecordType) -> bool:
        """Only MX records carry a priority field in Cloudflare's API."""
        return record_type == DnsRecordType.MX

    @staticmethod
    @rule
    def normalize_priority(record_type: DnsRecordType, priority: int | None) -> int | None:
        """Enforce 'required for MX, ignored otherwise' — never string-encode
        this into content; Cloudflare's API wants it as a sibling field."""
        if CloudflareDnsRules.requires_priority(record_type):
            if priority is None:
                raise MissingDnsRecordPriority()
            return priority
        return None


class DnsRecordSyncRules:
    """Pure mapping rules for Cloudflare → local DNS record type."""

    _CF_TYPE_MAP: dict[str, DnsRecordType] = {
        "A": DnsRecordType.A,
        "AAAA": DnsRecordType.AAAA,
        "CNAME": DnsRecordType.CNAME,
        "TXT": DnsRecordType.TXT,
        "MX": DnsRecordType.MX,
    }

    @staticmethod
    @rule
    def map_cf_type(cf_type: str) -> DnsRecordType:
        """Map a Cloudflare API record type string to local DnsRecordType enum."""
        return DnsRecordSyncRules._CF_TYPE_MAP.get(cf_type, DnsRecordType.OTHER)


class TunnelHostnameRules:
    """Pure decision rules for matching a Tunnel's public hostnames to the
    environments they actually serve. No I/O."""

    @staticmethod
    @rule
    def match_environment_id(hostname: str, candidates: list[tuple[UUID, str | None]]) -> UUID | None:
        """Return the id of the candidate environment whose base_url's host
        exactly matches hostname, or None if no candidate matches (including
        when every candidate has no base_url configured). Deterministic,
        exact-host comparison only — never a fuzzy/prefix match, since a
        wrong match here would leak one project's internal service URL onto
        another project's Tunnels page."""
        for environment_id, base_url in candidates:
            if base_url is None:
                continue
            if urlparse(base_url).hostname == hostname:
                return environment_id
        return None


class TunnelOwnershipRules:
    """Pure decision rules for whether a Tunnel belongs to the Cloudflare
    account an environment is bound to. Tunnels are account-scoped (many
    environments on the same account may legitimately manage the same
    tunnel's hostnames), so ownership is checked one level up from where it
    used to be checked (directly against environment_id, pre-fix)."""

    @staticmethod
    @rule
    def verify_tunnel_belongs_to_environment(
        tunnel: CloudflareTunnelRead | None, cloudflare_account_id: UUID
    ) -> bool:
        """True iff tunnel exists and is on the given Cloudflare account."""
        return tunnel is not None and tunnel.cloudflare_account_id == cloudflare_account_id


class TunnelSyncRules:
    """Pure mapping rules for Cloudflare → local tunnel status."""

    CF_STATUS_MAP: dict[str, TunnelStatus] = {
        "healthy": TunnelStatus.HEALTHY,
        "degraded": TunnelStatus.DEGRADED,
        "down": TunnelStatus.DOWN,
        "inactive": TunnelStatus.UNKNOWN,
    }

    @staticmethod
    @rule
    def map_cf_status(cf_status: str) -> TunnelStatus:
        """Map a Cloudflare API status string to local TunnelStatus enum."""
        return TunnelSyncRules.CF_STATUS_MAP.get(cf_status, TunnelStatus.UNKNOWN)
