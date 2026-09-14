"""Symmetric encryption mechanism for any module storing a secret at rest.

Generic on purpose: no key is hardcoded or read from settings here — each
module that stores a secret (auth, cloudflare, notifications, observability)
supplies its own Fernet key from its own config.py, keeping "core holds
mechanism, never a business concept" intact.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import SecretUnreadableError


class FernetCodec:
    """Encrypt/decrypt a string value with a caller supplied Fernet key."""

    @staticmethod
    def encrypt(plaintext: str, *, key: str) -> str:
        """Return the ciphertext for plaintext, encrypted with key."""
        return Fernet(key.encode()).encrypt(plaintext.encode()).decode()

    @staticmethod
    def decrypt(ciphertext: str, *, key: str) -> str:
        """Return the plaintext for ciphertext, decrypted with key. Raises
        SecretUnreadableError when the ciphertext was tampered with, was encrypted
        under another key, or key is not a valid Fernet key."""
        try:
            return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
        except (InvalidToken, ValueError) as exc:
            raise SecretUnreadableError() from exc
