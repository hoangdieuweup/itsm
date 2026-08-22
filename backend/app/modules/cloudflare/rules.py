"""Business rules for the cloudflare module.

Everything here is a pure decision: no I/O, no framework, no database.
"""

from app.core.base.markers import rule
from app.modules.cloudflare.constants import ACCESS_LEVEL_RANK, AccessLevel


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
        return ACCESS_LEVEL_RANK[held] >= ACCESS_LEVEL_RANK[required]

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
