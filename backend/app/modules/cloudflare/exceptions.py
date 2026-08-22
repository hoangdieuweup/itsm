"""Errors owned by the cloudflare module."""

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationFailedError,
)
from app.modules.cloudflare.constants import ErrorCode


class CloudflareAccountNotFound(NotFoundError):
    """Raised when no cloudflare account matches the requested id."""

    code = ErrorCode.ACCOUNT_NOT_FOUND
    message = "Cloudflare account not found"


class CloudflareAccountManagerNotFound(NotFoundError):
    """Raised when no manager row matches the requested (account_id, user_id)."""

    code = ErrorCode.MANAGER_NOT_FOUND
    message = "Cloudflare account manager not found"


class InvalidCloudflareToken(ValidationFailedError):
    """Raised when Cloudflare rejects the provided API token (bad token, or a
    200 response with the v4 envelope's success=false)."""

    code = ErrorCode.INVALID_TOKEN
    message = "Cloudflare rejected the provided API token"


class CloudflareApiUnavailable(IntegrationError):
    """Raised when the Cloudflare API cannot be reached or returns a server error."""

    code = ErrorCode.API_UNAVAILABLE
    message = "Cloudflare API unavailable"


class InsufficientAccountAccess(ForbiddenError):
    """Raised when the caller's per-account access_level does not satisfy the
    level required for the requested action."""

    code = ErrorCode.INSUFFICIENT_ACCESS
    message = "Insufficient access level on this Cloudflare account"


class LastOwnerRemovalBlocked(ConflictError):
    """Raised when removing or downgrading a manager row would leave zero
    OWNERs on the account."""

    code = ErrorCode.LAST_OWNER_REMOVAL_BLOCKED
    message = "Cannot remove or downgrade the last owner of this account"
