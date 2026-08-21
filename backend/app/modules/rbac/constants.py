"""Constants and enums owned by the rbac module."""

from enum import StrEnum


class RbacPermissionCatalog:
    """The fixed (resource, action, description) catalog — seeded from code,
    never admin-created. See rbac/seeds and references/rbac.md's anti-pattern
    list: permissions are what the application *can* do, not free text."""

    CATALOG: list[tuple[str, str, str]] = [
        ("role", "create", "Create a new role"),
        ("role", "read", "View roles and their permissions"),
        ("role", "update", "Rename a role or change its permission set"),
        ("role", "delete", "Delete a custom role"),
        ("permission", "read", "View the permission catalog"),
        ("user", "read", "View the user list"),
        ("user", "update_status", "Block or unblock a user"),
        ("user", "assign_role", "Assign a role to a user"),
    ]


class RbacDefaults:
    """Seeded role names. See seeds/seed_rbac.py."""

    OWNER_ROLE_NAME = "owner"
    ADMIN_ROLE_NAME = "admin"
    MEMBER_ROLE_NAME = "member"
    SYSTEM_ROLE_NAMES = (OWNER_ROLE_NAME, ADMIN_ROLE_NAME, MEMBER_ROLE_NAME)
    DEFAULT_ROLE_NAME = MEMBER_ROLE_NAME


class RbacLimits:
    """Numeric limits owned by the rbac module."""

    MAX_ROLE_NAME_LENGTH = 100


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    ROLE_NOT_FOUND = "rbac_role_not_found"
    DUPLICATE_ROLE_NAME = "rbac_duplicate_role_name"
    SYSTEM_ROLE_IMMUTABLE = "rbac_system_role_immutable"
    ROLE_IN_USE = "rbac_role_in_use"
    CANNOT_REMOVE_LAST_OWNER = "rbac_cannot_remove_last_owner"
    TARGET_USER_NOT_FOUND = "rbac_target_user_not_found"
    PERMISSION_DENIED = "rbac_permission_denied"
    UNKNOWN_PERMISSION_ID = "rbac_unknown_permission_id"
