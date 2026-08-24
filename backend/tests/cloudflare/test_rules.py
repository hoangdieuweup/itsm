"""Unit tests for app.modules.cloudflare.rules — pure functions, no I/O."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.cloudflare.constants import AccessLevel, DnsRecordType, TunnelStatus
from app.modules.cloudflare.exceptions import MissingDnsRecordPriority
from app.modules.cloudflare.rules import (
    CloudflareAccountRules,
    CloudflareDnsRules,
    TunnelHostnameRules,
    TunnelOwnershipRules,
)
from app.modules.cloudflare.schemas import CloudflareTunnelRead


class TestSatisfiesLevel:
    def test_owner_satisfies_viewer(self) -> None:
        assert CloudflareAccountRules.satisfies_level(AccessLevel.OWNER, AccessLevel.VIEWER) is True

    def test_editor_satisfies_editor(self) -> None:
        assert CloudflareAccountRules.satisfies_level(AccessLevel.EDITOR, AccessLevel.EDITOR) is True

    def test_viewer_does_not_satisfy_owner(self) -> None:
        assert CloudflareAccountRules.satisfies_level(AccessLevel.VIEWER, AccessLevel.OWNER) is False

    def test_none_always_satisfies(self) -> None:
        """None means the caller passed via the manage_all Layer-1 bypass."""
        assert CloudflareAccountRules.satisfies_level(None, AccessLevel.OWNER) is True


class TestRequiredLevelForUpdate:
    def test_rotating_token_requires_owner(self) -> None:
        assert CloudflareAccountRules.required_level_for_update(rotates_token=True) is AccessLevel.OWNER

    def test_label_only_requires_editor(self) -> None:
        assert CloudflareAccountRules.required_level_for_update(rotates_token=False) is AccessLevel.EDITOR


class TestBlocksLastOwnerRemoval:
    def test_blocks_when_only_owner_remains(self) -> None:
        assert CloudflareAccountRules.blocks_last_owner_removal(AccessLevel.OWNER, 1) is True

    def test_allows_when_multiple_owners_remain(self) -> None:
        assert CloudflareAccountRules.blocks_last_owner_removal(AccessLevel.OWNER, 2) is False

    def test_allows_removing_a_non_owner(self) -> None:
        assert CloudflareAccountRules.blocks_last_owner_removal(AccessLevel.EDITOR, 1) is False


class TestRequiresPriority:
    def test_mx_requires_priority(self) -> None:
        assert CloudflareDnsRules.requires_priority(DnsRecordType.MX) is True

    def test_a_record_does_not_require_priority(self) -> None:
        assert CloudflareDnsRules.requires_priority(DnsRecordType.A) is False


class TestNormalizePriority:
    def test_mx_with_priority_keeps_it(self) -> None:
        assert CloudflareDnsRules.normalize_priority(DnsRecordType.MX, 10) == 10

    def test_mx_without_priority_raises(self) -> None:
        with pytest.raises(MissingDnsRecordPriority):
            CloudflareDnsRules.normalize_priority(DnsRecordType.MX, None)

    def test_non_mx_with_priority_is_forced_to_none(self) -> None:
        assert CloudflareDnsRules.normalize_priority(DnsRecordType.CNAME, 10) is None

    def test_non_mx_without_priority_stays_none(self) -> None:
        assert CloudflareDnsRules.normalize_priority(DnsRecordType.A, None) is None


class TestMatchEnvironmentId:
    def test_exact_host_match(self) -> None:
        env_id = uuid4()
        candidates: list[tuple[UUID, str | None]] = [(env_id, "https://agent-mkt.agentsplatform.cloud")]
        assert (
            TunnelHostnameRules.match_environment_id("agent-mkt.agentsplatform.cloud", candidates) == env_id
        )

    def test_no_match_returns_none(self) -> None:
        candidates: list[tuple[UUID, str | None]] = [(uuid4(), "https://agent-mkt.agentsplatform.cloud")]
        assert TunnelHostnameRules.match_environment_id("itsm.agentsplatform.cloud", candidates) is None

    def test_environment_with_no_base_url_never_matches(self) -> None:
        candidates: list[tuple[UUID, str | None]] = [(uuid4(), None)]
        assert TunnelHostnameRules.match_environment_id("itsm.agentsplatform.cloud", candidates) is None

    def test_empty_candidates_returns_none(self) -> None:
        assert TunnelHostnameRules.match_environment_id("itsm.agentsplatform.cloud", []) is None

    def test_picks_the_correct_candidate_among_several(self) -> None:
        agent_mkt_id, itsm_id = uuid4(), uuid4()
        candidates: list[tuple[UUID, str | None]] = [
            (agent_mkt_id, "https://agent-mkt.agentsplatform.cloud"),
            (itsm_id, "https://itsm.agentsplatform.cloud"),
        ]
        assert TunnelHostnameRules.match_environment_id("itsm.agentsplatform.cloud", candidates) == itsm_id

    def test_never_fuzzy_or_prefix_matches(self) -> None:
        """A wrong match here would leak one project's internal service URL
        onto another project's Tunnels page — must be exact-host only."""
        candidates: list[tuple[UUID, str | None]] = [(uuid4(), "https://agent-mkt.agentsplatform.cloud")]
        assert (
            TunnelHostnameRules.match_environment_id("agent-mkt.agentsplatform.cloud.evil.com", candidates)
            is None
        )
        assert TunnelHostnameRules.match_environment_id("mkt.agentsplatform.cloud", candidates) is None


def _make_tunnel(cloudflare_account_id) -> CloudflareTunnelRead:
    now = datetime.now(UTC)
    return CloudflareTunnelRead(
        id=uuid4(),
        cloudflare_account_id=cloudflare_account_id,
        cf_tunnel_id="tun-1",
        name="prod-tunnel",
        status=TunnelStatus.UNKNOWN,
        last_synced_at=None,
        created_at=now,
        updated_at=now,
    )


class TestVerifyTunnelBelongsToEnvironment:
    def test_true_when_same_account(self) -> None:
        account_id = uuid4()
        tunnel = _make_tunnel(account_id)
        assert TunnelOwnershipRules.verify_tunnel_belongs_to_environment(tunnel, account_id) is True

    def test_false_when_different_account(self) -> None:
        tunnel = _make_tunnel(uuid4())
        assert TunnelOwnershipRules.verify_tunnel_belongs_to_environment(tunnel, uuid4()) is False

    def test_false_when_tunnel_is_none(self) -> None:
        assert TunnelOwnershipRules.verify_tunnel_belongs_to_environment(None, uuid4()) is False
