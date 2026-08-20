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


class DxDefaults:
    """Numeric defaults owned by the dx_core integration."""

    PKCE_STATE_TTL_SECONDS = 600
    CODE_VERIFIER_BYTES = 64
    STATE_BYTES = 32
    # How long one caller may hold the per-user refresh mutex before another
    # caller is allowed to steal it (crash safety, not the expected duration).
    REFRESH_LOCK_TTL_SECONDS = 10
    # A waiter re-checks app.integrations.dx_core.repository's cached token
    # this often while another request holds the refresh mutex.
    REFRESH_LOCK_POLL_INTERVAL_SECONDS = 0.2
    REFRESH_LOCK_MAX_WAIT_SECONDS = 5
    # Treat a DX access token as expired this many seconds before its actual
    # expires_at, so a request never races the upstream server's own clock.
    ACCESS_TOKEN_EXPIRY_SKEW_SECONDS = 30
    CALLBACK_HTTP_TIMEOUT_SECONDS = 10.0


class DxCacheNamespaces:
    """Redis key namespaces owned by the dx_core integration.

    Passed to CacheKeyBuilder.session_key(namespace, identifier) — see
    app/integrations/cache/keys.py; no other file constructs these keys.
    """

    PKCE_STATE = "dx:pkce"
    REFRESH_LOCK = "dx:refresh_lock"


class DxErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UNAVAILABLE = "dx_core_unavailable"
    INVALID_STATE = "dx_core_invalid_state"
    TOKEN_EXCHANGE_FAILED = "dx_core_token_exchange_failed"
    NOT_LINKED = "dx_core_not_linked"
    REFRESH_FAILED = "dx_core_refresh_failed"
