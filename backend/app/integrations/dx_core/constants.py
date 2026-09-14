"""Constants owned by the dx_core integration.

DX endpoint paths are hardcoded here rather than configured, per
docs/tasks/sso-login.md section 3 ("DX Endpoints (hardcoded trong code)") —
only the base URL and credentials are environment driven.
"""

from enum import StrEnum


class DxEndpoints:
    """Fixed paths on the DX OAuth2 server, joined with DX_CORE__API_BASE_URL."""

    AUTHORIZE = "/oauth2/authorize"
    TOKEN = "/oauth2/token"
    USERINFO = "/oauth2/userinfo"
    REVOKE = "/oauth2/revoke"
    LOGOUT = "/oauth2/logout"


class DxDefaults:
    """Numeric defaults owned by the dx_core integration."""

    PKCE_STATE_TTL_SECONDS = 600
    CODE_VERIFIER_BYTES = 64
    STATE_BYTES = 32
    CALLBACK_HTTP_TIMEOUT_SECONDS = 10.0


class DxCacheNamespaces:
    """Redis key namespaces owned by the dx_core integration.

    Passed to CacheKeyBuilder.session_key(namespace, identifier) — see
    app/integrations/cache/keys.py; no other file constructs these keys.
    """

    PKCE_STATE = "dx:pkce"


class DxErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UNAVAILABLE = "dx_core_unavailable"
    INVALID_STATE = "dx_core_invalid_state"
    TOKEN_EXCHANGE_FAILED = "dx_core_token_exchange_failed"
