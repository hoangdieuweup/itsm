"""Errors owned by the auth module.

These live here rather than in a global module because each one encodes a
fact about auth: what counts as missing, what counts as blocked. The
mechanism they build on lives in app.exceptions.
"""

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from app.modules.auth.constants import ErrorCode


class UserNotFound(NotFoundError):
    """Raised when no user matches the requested identifier."""

    code = ErrorCode.USER_NOT_FOUND
    message = "User not found"


class UserBlocked(ForbiddenError):
    """Raised when a blocked user attempts to sign in or use a session."""

    code = ErrorCode.USER_BLOCKED
    message = "User account is blocked"


class InvalidCredentials(ValidationFailedError):
    """Raised when a login attempt fails validation (bad state, bad token, ...)."""

    code = ErrorCode.INVALID_CREDENTIALS
    message = "Invalid credentials"


class NotAuthenticated(ForbiddenError):
    """Raised when a request requires a session that isn't present or is invalid."""

    code = ErrorCode.NOT_AUTHENTICATED
    status_code = 401
    message = "Authentication required"


class CannotBlockLastAdmin(ForbiddenError):
    """Raised when blocking this user would leave zero users holding the admin role."""

    code = ErrorCode.CANNOT_BLOCK_LAST_ADMIN
    message = "This is the last user with the admin role — reassign it before blocking them"
