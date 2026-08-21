"""Constants and enums owned by the users module."""

from enum import StrEnum


class UserLimits:
    """Numeric limits owned by the users module."""

    MAX_NAME_LENGTH = 255
    MAX_EMAIL_LENGTH = 320
    MAX_EMPLOYEE_CODE_LENGTH = 64
    DEFAULT_PAGE_SIZE = 50


class UsersEvents:
    """Messaging identity owned by the users module. See references/messaging.md."""

    EXCHANGE = "users"


class UsersCacheKeys:
    """Cache identity owned by the users module. See references/caching.md.

    ENTITY stays "user" (not "users") — it's the Redis key prefix, already
    live from the auth-module caching work; renaming it would just orphan
    warm cache entries for no benefit.
    """

    ENTITY = "user"
    TTL_SECONDS = 300


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    USER_NOT_FOUND = "users_user_not_found"
    CANNOT_BLOCK_LAST_ADMIN = "users_cannot_block_last_admin"
    CANNOT_MODIFY_PROTECTED_ADMIN = "users_cannot_modify_protected_admin"
