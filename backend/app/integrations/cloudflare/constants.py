"""Constants owned by the cloudflare integration."""

from enum import StrEnum


class CloudflareErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UNAVAILABLE = "cloudflare_api_unavailable"
    INVALID_TOKEN = "cloudflare_invalid_token"
    DNS_OPERATION_REJECTED = "cloudflare_dns_operation_rejected"
