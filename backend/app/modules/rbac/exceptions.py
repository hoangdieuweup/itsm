"""Errors owned by the rbac module."""

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from app.modules.rbac.constants import ErrorCode


class RoleNotFound(NotFoundError):
    """Raised when no role matches the requested id."""

    code = ErrorCode.ROLE_NOT_FOUND
    message = "Role not found"


class DuplicateRoleName(ConflictError):
    """Raised when a role name is already taken."""

    code = ErrorCode.DUPLICATE_ROLE_NAME
    message = "A role with this name already exists"


class SystemRoleImmutable(ForbiddenError):
    """Raised when renaming or deleting one of the seeded admin/member roles."""

    code = ErrorCode.SYSTEM_ROLE_IMMUTABLE
    message = "This role's name cannot be changed and it cannot be deleted"


class RoleInUse(ConflictError):
    """Raised when deleting a role that still has users assigned to it."""

    code = ErrorCode.ROLE_IN_USE
    message = "This role still has users assigned to it"


class CannotRemoveLastAdmin(ValidationFailedError):
    """Raised when an action would leave zero users holding the admin role."""

    code = ErrorCode.CANNOT_REMOVE_LAST_ADMIN
    message = "This is the last user with the admin role — assign it to someone else first"


class CannotModifyProtectedAdmin(ForbiddenError):
    """Raised when attempting to reassign the role of the seeded break-glass
    admin account — its role is permanently locked."""

    code = ErrorCode.CANNOT_MODIFY_PROTECTED_ADMIN
    message = "This account's role is permanently locked and cannot be changed"


class TargetUserNotFound(NotFoundError):
    """Raised when assigning a role to a user id that doesn't exist in auth."""

    code = ErrorCode.TARGET_USER_NOT_FOUND
    message = "User not found"


class PermissionDenied(ForbiddenError):
    """Raised by require_permission when the current user's role lacks resource.action."""

    code = ErrorCode.PERMISSION_DENIED
    message = "Missing permission"


class UnknownPermissionId(ValidationFailedError):
    """Raised when a role create/update references a permission id not in the catalog."""

    code = ErrorCode.UNKNOWN_PERMISSION_ID
    message = "Unknown permission id"
