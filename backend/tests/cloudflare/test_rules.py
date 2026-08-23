"""Unit tests for app.modules.cloudflare.rules — pure functions, no I/O."""

import pytest

from app.modules.cloudflare.constants import AccessLevel, DnsRecordType
from app.modules.cloudflare.exceptions import MissingDnsRecordPriority
from app.modules.cloudflare.rules import CloudflareAccountRules, CloudflareDnsRules


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
