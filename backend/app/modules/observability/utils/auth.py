"""Authorization header builder for Loki requests."""

import base64

from app.core.base.markers import helper
from app.modules.observability.constants import LokiAuthType
from app.modules.observability.schemas import LokiConfigRead


class LokiAuthHelper:
    """Non-business helper for resolving Loki authentication headers."""

    @staticmethod
    @helper
    def resolve_loki_auth_header(config: LokiConfigRead, credential: str | None) -> str | None:
        """Builds the fully-formed Authorization header value for a Loki
        request, or None for no auth. credential is already decrypted by the
        repository. Returns None whenever no credential is on hand, even if
        auth_type suggests one should exist — the caller (a repository read) is
        the source of truth for whether a credential is actually stored."""
        if config.auth_type == LokiAuthType.NONE or credential is None:
            return None
        if config.auth_type == LokiAuthType.BEARER:
            return f"Bearer {credential}"
        if config.auth_type == LokiAuthType.BASIC:
            return f"Basic {base64.b64encode(credential.encode()).decode()}"
        return None
