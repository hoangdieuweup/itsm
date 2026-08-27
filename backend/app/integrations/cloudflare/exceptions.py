"""Errors owned by the cloudflare integration — transport/protocol failures
only. Domain-level errors (CloudflareAccountNotFound, ZoneNotOwnedByAccount,
etc.) live in app.modules.cloudflare.exceptions instead."""

from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.cloudflare.constants import CloudflareErrorCode


class CloudflareApiUnavailable(IntegrationError):
    """Raised when the Cloudflare API cannot be reached or returns a server error."""

    code = CloudflareErrorCode.UNAVAILABLE
    message = "Cloudflare API unavailable"


class InvalidCloudflareToken(ValidationFailedError):
    """Raised when Cloudflare rejects the provided API token (bad token, or a
    200 response with the v4 envelope's success=false)."""

    code = CloudflareErrorCode.INVALID_TOKEN
    message = "Cloudflare rejected the provided API token"


class CloudflareDnsOperationRejected(ValidationFailedError):
    """Raised when Cloudflare itself rejects a DNS write (malformed record,
    conflicting name, etc.) — distinct from InvalidCloudflareToken, which is
    specifically about authentication."""

    code = CloudflareErrorCode.DNS_OPERATION_REJECTED
    message = "Cloudflare rejected this DNS record operation"


class CloudflareAnalyticsQueryRejected(ValidationFailedError):
    """Raised when Cloudflare's GraphQL Analytics API returns a body-level
    `errors` array (e.g. a token missing the Zone:Analytics:Read permission,
    or a malformed query) — distinct from InvalidCloudflareToken (401/403 at
    the HTTP layer) and CloudflareDnsOperationRejected (the REST v4
    envelope's success=false), because GraphQL's own error shape is neither."""

    code = CloudflareErrorCode.ANALYTICS_QUERY_REJECTED
    message = "Cloudflare rejected this analytics query"
