"""Symmetric encryption mechanism for any module storing a secret at rest.

Generic on purpose: no key is hardcoded or read from settings here — the
owning integration (app/integrations/dx_core/config.py, the only current
consumer) supplies its own Fernet key, keeping "core holds mechanism, never
a business concept" intact.
"""

from cryptography.fernet import Fernet


class FernetCodec:
    """Encrypt/decrypt a string value with a caller supplied Fernet key.

    Raises cryptography.fernet.InvalidToken on decrypt when the ciphertext
    was tampered with or the key is wrong — the caller maps that to its own
    domain error.
    """

    @staticmethod
    def encrypt(plaintext: str, *, key: str) -> str:
        """Return the ciphertext for plaintext, encrypted with key."""
        return Fernet(key.encode()).encrypt(plaintext.encode()).decode()

    @staticmethod
    def decrypt(ciphertext: str, *, key: str) -> str:
        """Return the plaintext for ciphertext, decrypted with key."""
        return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
