"""Errors owned by the auth module.

These live here rather than in a global module because each one encodes a
fact about auth: what counts as blocked, what counts as not-signed-in. The
mechanism they build on lives in app.exceptions.
"""

from app.core.exceptions import ForbiddenError, ValidationFailedError
from app.modules.auth.constants import ErrorCode


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
