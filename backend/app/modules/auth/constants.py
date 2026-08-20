"""Constants and enums owned by the auth module.

Other modules import these with an explicit alias:
    from app.auth import constants as auth_constants
"""

from enum import StrEnum


class UserRole(StrEnum):
    """Application role a user is granted after sign in."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class UserStatus(StrEnum):
    """Lifecycle state of a user account."""

    ACTIVE = "active"
    PENDING = "pending"
    BLOCKED = "blocked"


class AuthLimits:
    """Numeric limits owned by the auth module."""

    MAX_NAME_LENGTH = 255
    MAX_EMAIL_LENGTH = 320
    MAX_EMPLOYEE_CODE_LENGTH = 64
    DEFAULT_PAGE_SIZE = 50


class AuthEvents:
    """Messaging identity owned by the auth module. See references/messaging.md."""

    EXCHANGE = "auth"


class AuthCookies:
    """Cookie names owned by the auth module's session."""

    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"


class AuthCacheNamespaces:
    """Redis key namespaces owned by the auth module.

    Passed to CacheKeyBuilder.session_key(namespace, identifier) — see
    app/integrations/cache/keys.py; no other file constructs these keys.
    """

    TOKEN_BLACKLIST = "auth:blacklist"


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    USER_NOT_FOUND = "auth_user_not_found"
    USER_BLOCKED = "auth_user_blocked"
    INVALID_CREDENTIALS = "auth_invalid_credentials"
    NOT_AUTHENTICATED = "auth_not_authenticated"


class LoginPolicy:
    """Statuses that must never be allowed to complete a login, regardless of role."""

    BLOCKED_STATUSES: frozenset[UserStatus] = frozenset({UserStatus.BLOCKED})


class RoleMapping:
    """DX external role code -> application UserRole. See docs/tasks/sso-login.md #8."""

    EXTERNAL_ROLE_MAP: dict[str, UserRole] = {
        "director": UserRole.OWNER,
        "manager": UserRole.ADMIN,
        "employee": UserRole.MEMBER,
    }
    DEFAULT_EXTERNAL_ROLE_CODE = "employee"
