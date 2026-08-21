"""Unit tests for app.modules.users.rules — pure decisions, no I/O, no fixtures."""

from app.modules.users.config import users_settings
from app.modules.users.rules import UsersRules


class TestIsProtectedAdminEmail:
    def test_true_when_email_matches_configured_admin(self, monkeypatch) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", "admin@example.com")
        assert UsersRules.is_protected_admin_email("admin@example.com") is True

    def test_false_when_email_does_not_match(self, monkeypatch) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", "admin@example.com")
        assert UsersRules.is_protected_admin_email("someone-else@example.com") is False

    def test_false_when_admin_email_unset(self, monkeypatch) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", None)
        assert UsersRules.is_protected_admin_email("anyone@example.com") is False
