"""Unit tests for app.auth.rules — pure decisions, no I/O, no fixtures."""

import pytest

from app.modules.auth.config import auth_settings
from app.modules.auth.constants import UserStatus
from app.modules.auth.rules import AuthRules


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (UserStatus.ACTIVE, True),
        (UserStatus.PENDING, True),
        (UserStatus.BLOCKED, False),
    ],
)
def test_can_login(status: UserStatus, expected: bool) -> None:
    """Only a blocked user is denied login; every other status is allowed through."""
    assert AuthRules.can_login(status) is expected


class TestIsProtectedAdminEmail:
    def test_true_when_email_matches_configured_admin(self, monkeypatch) -> None:
        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", "admin@example.com")
        assert AuthRules.is_protected_admin_email("admin@example.com") is True

    def test_false_when_email_does_not_match(self, monkeypatch) -> None:
        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", "admin@example.com")
        assert AuthRules.is_protected_admin_email("someone-else@example.com") is False

    def test_false_when_admin_email_unset(self, monkeypatch) -> None:
        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", None)
        assert AuthRules.is_protected_admin_email("anyone@example.com") is False
