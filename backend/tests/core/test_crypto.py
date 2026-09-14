"""Unit tests for app.core.crypto."""

import pytest
from cryptography.fernet import Fernet

from app.core.crypto import FernetCodec
from app.core.exceptions import SecretUnreadableError


def _key() -> str:
    return Fernet.generate_key().decode()


class TestFernetCodec:
    def test_round_trips_a_value(self) -> None:
        key = _key()

        assert FernetCodec.decrypt(FernetCodec.encrypt("secret", key=key), key=key) == "secret"

    def test_another_key_raises_secret_unreadable(self) -> None:
        ciphertext = FernetCodec.encrypt("secret", key=_key())

        with pytest.raises(SecretUnreadableError):
            FernetCodec.decrypt(ciphertext, key=_key())

    def test_an_empty_key_raises_secret_unreadable(self) -> None:
        ciphertext = FernetCodec.encrypt("secret", key=_key())

        with pytest.raises(SecretUnreadableError):
            FernetCodec.decrypt(ciphertext, key="")

    def test_a_tampered_ciphertext_raises_secret_unreadable(self) -> None:
        with pytest.raises(SecretUnreadableError):
            FernetCodec.decrypt("not-a-fernet-token", key=_key())
