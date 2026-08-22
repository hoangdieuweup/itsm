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


class CloudflareConfigNotFound(NotFoundError):
    """Raised when no cloudflare_configs row exists for the requested environment."""

    code = ErrorCode.CONFIG_NOT_FOUND
    message = "This environment is not bound to a Cloudflare account/zone"


class CloudflareConfigAlreadyExists(ConflictError):
    """Raised when an environment already has a binding (environment_id is UNIQUE)."""

    code = ErrorCode.CONFIG_ALREADY_EXISTS
    message = "This environment is already bound to a Cloudflare account/zone"


class CloudflareEnvironmentNotFound(NotFoundError):
    """Raised when the referenced environment_id does not exist. Module-local
    on purpose — cloudflare defines its own rather than importing projects'
    EnvironmentNotFound, keeping cross-module coupling to data only."""

    code = ErrorCode.ENVIRONMENT_NOT_FOUND
    message = "Environment not found"


class DnsRecordNotFound(NotFoundError):
    """Raised when no dns_records row matches the requested id for this environment."""

    code = ErrorCode.DNS_RECORD_NOT_FOUND
    message = "DNS record not found"


class ZoneNotOwnedByAccount(ValidationFailedError):
    """Raised when the submitted zone_id does not appear in the target
    account's own zone list — blocks cross-account zone spoofing."""

    code = ErrorCode.ZONE_NOT_OWNED_BY_ACCOUNT
    message = "This zone does not belong to the selected Cloudflare account"


class MissingDnsRecordPriority(ValidationFailedError):
    """Raised when record_type=MX and no priority was supplied."""

    code = ErrorCode.MISSING_DNS_PRIORITY
    message = "MX records require a priority value"


class CloudflareDnsOperationRejected(ValidationFailedError):
    """Raised when Cloudflare itself rejects a DNS write (malformed record,
    conflicting name, etc.) — distinct from InvalidCloudflareToken, which is
    specifically about authentication."""

    code = ErrorCode.DNS_OPERATION_REJECTED
    message = "Cloudflare rejected this DNS record operation"


class DnsRecordSyncFailed(IntegrationError):
    """Raised when Cloudflare's side of a write succeeded but the local
    Postgres write then failed. See Decision #3: this must never degrade
    silently, unlike audit's fire-and-forget philosophy — a dns_records row
    is primary state. A compensating action is attempted first where
    possible (create/update); delete has none."""

    code = ErrorCode.DNS_SYNC_FAILED
    message = "Cloudflare was updated but the local record failed to save — check logs for details"


class DnsRecordsExistForConfig(ConflictError):
    """Raised when deleting a binding would orphan existing dns_records rows —
    they must be deleted first."""

    code = ErrorCode.DNS_RECORDS_EXIST_FOR_CONFIG
    message = "Delete this environment's DNS records before removing its Cloudflare binding"
