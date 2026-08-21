"""Errors owned by the users module."""

from app.core.exceptions import ForbiddenError, NotFoundError
from app.modules.users.constants import ErrorCode


class UserNotFound(NotFoundError):
    """Raised when no user matches the requested identifier."""

    code = ErrorCode.USER_NOT_FOUND
    message = "User not found"


class CannotBlockLastAdmin(ForbiddenError):
    """Raised when blocking this user would leave zero users holding the admin role."""

    code = ErrorCode.CANNOT_BLOCK_LAST_ADMIN
    message = "This is the last user with the admin role — reassign it before blocking them"


class CannotModifyProtectedAdmin(ForbiddenError):
    """Raised when attempting to block the seeded break-glass admin account."""

    code = ErrorCode.CANNOT_MODIFY_PROTECTED_ADMIN
    message = "This account is permanently protected and cannot be blocked"
