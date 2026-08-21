"""Constants and enums owned by the rbac module."""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any


class RbacPermissionCatalog:
    """The fixed (resource, action, description_key) catalog — seeded from
    code, never admin-created. See rbac/seeds and references/rbac.md's
    anti-pattern list: permissions are what the application *can* do, not
    free text.

    description_key is an i18n key (e.g. "permissions.role.create"), not
    display text — the frontend owns the actual translated string under its
    own "rbac" message namespace, the same way error codes are keys the
    frontend maps to copy, never raw text from the backend. See
    Permission's docstring in models.py.
    """

    CATALOG: list[tuple[str, str, str]] = [
        ("role", "create", "permissions.role.create"),
        ("role", "read", "permissions.role.read"),
        ("role", "update", "permissions.role.update"),
        ("role", "delete", "permissions.role.delete"),
        ("permission", "read", "permissions.permission.read"),
        ("user", "read", "permissions.user.read"),
        ("user", "update_status", "permissions.user.update_status"),
        ("user", "assign_role", "permissions.user.assign_role"),
    ]


class RbacDefaults:
    """Seeded role names. See seeds/seed_rbac.py.

    No OWNER_ROLE_NAME: this system has no "owner" role — admin is the
    highest seeded role, and the bus-factor protection (RbacRules.
    blocks_last_admin_removal) guards admin, not a role nothing creates.
    """

    ADMIN_ROLE_NAME = "admin"
    MEMBER_ROLE_NAME = "member"
    SYSTEM_ROLE_NAMES = (ADMIN_ROLE_NAME, MEMBER_ROLE_NAME)
    DEFAULT_ROLE_NAME = MEMBER_ROLE_NAME


class RbacCacheKeys:
    """Cache identity owned by the rbac module. See references/caching.md."""

    ROLE_ENTITY = "role"
    USER_ROLE_ENTITY = "user_role"
    TTL_SECONDS = 300


class RbacLimits:
    """Numeric limits owned by the rbac module."""

    MAX_ROLE_NAME_LENGTH = 100


class RbacTypes:
    """Type aliases owned by the rbac module."""

    UserLookup = Callable[[int], Awaitable[Any | None]]
    ProtectionCheck = Callable[[int], Awaitable[bool]]


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    ROLE_NOT_FOUND = "rbac_role_not_found"
    DUPLICATE_ROLE_NAME = "rbac_duplicate_role_name"
    SYSTEM_ROLE_IMMUTABLE = "rbac_system_role_immutable"
    ROLE_IN_USE = "rbac_role_in_use"
    CANNOT_REMOVE_LAST_ADMIN = "rbac_cannot_remove_last_admin"
    CANNOT_MODIFY_PROTECTED_ADMIN = "rbac_cannot_modify_protected_admin"
    TARGET_USER_NOT_FOUND = "rbac_target_user_not_found"
    PERMISSION_DENIED = "rbac_permission_denied"
    UNKNOWN_PERMISSION_ID = "rbac_unknown_permission_id"
