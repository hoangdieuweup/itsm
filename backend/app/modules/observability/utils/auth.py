"""Authorization header builder for Loki requests."""

import base64

from app.core.base.markers import helper
from app.core.crypto import FernetCodec
from app.modules.observability.config import observability_settings
from app.modules.observability.constants import LokiAuthType
from app.modules.observability.schemas import LokiConfigRead


class LokiAuthHelper:
    """Non-business helper for resolving Loki authentication headers."""

    @staticmethod
    @helper
    def resolve_loki_auth_header(config: LokiConfigRead, ciphertext: str | None) -> str | None:
        """Builds the fully-formed Authorization header value for a Loki
        request, or None for no auth. Returns None whenever no ciphertext is on
        hand, even if auth_type suggests one should exist — the caller (a
        repository read) is the source of truth for whether a credential is
        actually stored, not this function."""
        if config.auth_type == LokiAuthType.NONE or ciphertext is None:
            return None
        plaintext = FernetCodec.decrypt(ciphertext, key=observability_settings.FERNET_KEY)
        if config.auth_type == LokiAuthType.BEARER:
            return f"Bearer {plaintext}"
        if config.auth_type == LokiAuthType.BASIC:
            return f"Basic {base64.b64encode(plaintext.encode()).decode()}"
        return None
