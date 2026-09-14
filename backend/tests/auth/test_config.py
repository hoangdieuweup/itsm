"""Unit tests for app.modules.auth.config — environment resolution only, no .env file."""

import pytest

from app.modules.auth.config import AuthConfig


class TestDxTokenFernetKey:
    @pytest.fixture(autouse=True)
    def _clear_key_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("AUTH__DX_TOKEN_FERNET_KEY", "DX_CORE__FERNET_KEY"):
            monkeypatch.delenv(name, raising=False)

    def test_reads_the_auth_prefixed_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH__DX_TOKEN_FERNET_KEY", "new-key")

        assert AuthConfig(_env_file=None).DX_TOKEN_FERNET_KEY.get_secret_value() == "new-key"

    def test_falls_back_to_the_former_dx_core_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An env file that still names the key DX_CORE__FERNET_KEY keeps decrypting stored tokens."""
        monkeypatch.setenv("DX_CORE__FERNET_KEY", "old-key")

        assert AuthConfig(_env_file=None).DX_TOKEN_FERNET_KEY.get_secret_value() == "old-key"

    def test_prefers_the_auth_prefixed_key_when_both_are_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH__DX_TOKEN_FERNET_KEY", "new-key")
        monkeypatch.setenv("DX_CORE__FERNET_KEY", "old-key")

        assert AuthConfig(_env_file=None).DX_TOKEN_FERNET_KEY.get_secret_value() == "new-key"

    def test_keeps_the_key_out_of_the_settings_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH__DX_TOKEN_FERNET_KEY", "new-key")

        assert "new-key" not in repr(AuthConfig(_env_file=None))
