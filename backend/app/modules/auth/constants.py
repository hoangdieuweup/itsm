"""Constants and enums owned by the auth module.

Other modules import these with an explicit alias:
    from app.auth import constants as auth_constants
"""

from enum import StrEnum
from typing import Literal

from app.modules.common.public import UserStatus


class AuthEvents:
    """Messaging identity owned by the auth module. See references/messaging.md."""

    EXCHANGE = "auth"


class AuthCookies:
    """Cookie names owned by the auth module's session."""

    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"

    SameSite = Literal["lax", "none", "strict"]


class AuthCacheNamespaces:
    """Redis key namespaces owned by the auth module.

    Passed to CacheKeyBuilder.session_key(namespace, identifier) — see
    app/integrations/cache/keys.py; no other file constructs these keys.
    """

    TOKEN_BLACKLIST = "auth:blacklist"


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    INVALID_CREDENTIALS = "auth_invalid_credentials"
    NOT_AUTHENTICATED = "auth_not_authenticated"
    USER_BLOCKED = "auth_user_blocked"


class LoginPolicy:
    """Statuses that must never be allowed to complete a login, regardless of role."""

    BLOCKED_STATUSES: frozenset[UserStatus] = frozenset({UserStatus.BLOCKED})
