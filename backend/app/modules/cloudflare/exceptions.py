"""Errors owned by the cloudflare module. Transport/protocol-level errors
(CloudflareApiUnavailable, InvalidCloudflareToken, CloudflareDnsOperationRejected)
live in app.integrations.cloudflare.exceptions instead — they originate in
the Cloudflare REST client, not a business decision this module owns."""

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    SecretUnreadableError,
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


class EnvironmentBaseUrlNotConfigured(ValidationFailedError):
    """Raised when traffic stats are requested for an environment with no
    base_url set — there is no hostname to filter Cloudflare's zone-wide
    traffic down to (same sharing concern DNS/Tunnel hostname matching
    already solved this session)."""

    code = ErrorCode.ENVIRONMENT_BASE_URL_NOT_CONFIGURED
    message = "This environment has no base URL configured"


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


class CloudflareTunnelNotFound(NotFoundError):
    """Raised when no cloudflare_tunnels row matches the requested id for this environment."""

    code = ErrorCode.TUNNEL_NOT_FOUND
    message = "Cloudflare Tunnel not found"


class TunnelPublicHostnameNotFound(NotFoundError):
    """Raised when no tunnel_public_hostnames row matches the requested id for this tunnel."""

    code = ErrorCode.TUNNEL_HOSTNAME_NOT_FOUND
    message = "Tunnel public hostname not found"


class TunnelConfigLocked(ConflictError):
    """Raised when another request already holds the per-tunnel ingress lock
    (Decision #1 — reject immediately, never poll-and-wait)."""

    code = ErrorCode.TUNNEL_CONFIG_LOCKED
    message = "Another request is currently editing this tunnel's configuration — try again shortly"


class TunnelHostnameAlreadyExists(ConflictError):
    """Raised when the submitted hostname already exists in the tunnel's ingress array."""

    code = ErrorCode.TUNNEL_HOSTNAME_ALREADY_EXISTS
    message = "This hostname is already published on this tunnel"


class TunnelHostnameDomainMismatch(ValidationFailedError):
    """Raised when the submitted hostname's domain does not match the
    environment's bound Cloudflare zone. The frontend only offers a
    subdomain field and appends the bound zone itself, but that's a UX
    constraint, not a security boundary — this is the server-side check
    that actually enforces it, mirroring ZoneNotOwnedByAccount's role for
    DNS record binding."""

    code = ErrorCode.TUNNEL_HOSTNAME_DOMAIN_MISMATCH
    message = "This hostname's domain does not match the environment's bound Cloudflare zone"


class TunnelHostnameEnvironmentMismatch(ValidationFailedError):
    """Raised when the submitted hostname exactly matches a DIFFERENT
    sibling environment's own base_url — a project-role holder attempting
    to claim a hostname that genuinely belongs to another project sharing
    the same Cloudflare account/tunnel. Distinct from
    TunnelHostnameDomainMismatch, which checks the zone, not ownership of
    a specific hostname within it."""

    code = ErrorCode.TUNNEL_HOSTNAME_ENVIRONMENT_MISMATCH
    message = "This hostname belongs to a different environment"


class TunnelIngressSyncFailed(IntegrationError):
    """Raised when Cloudflare's side of an ingress PUT succeeded but the
    local Postgres write then failed. Decision #5: a compensating PUT-back
    is attempted first; this must never degrade silently."""

    code = ErrorCode.TUNNEL_INGRESS_SYNC_FAILED
    message = "Cloudflare was updated but the local record failed to save — check logs for details"


class CloudflareAccountTokenUnreadable(SecretUnreadableError):
    """Raised when an account's stored API token can't be decrypted with the current
    CLOUDFLARE__FERNET_KEY — it was saved under a different key, or no valid key is set.
    An admin has to re-enter the token for that account."""

    code = ErrorCode.ACCOUNT_TOKEN_UNREADABLE
    message = "Stored Cloudflare API token cannot be decrypted with the current key"


class CloudflareWebhookSecretUnreadable(SecretUnreadableError):
    """Raised when an account's stored webhook secret can't be decrypted. The webhook
    destination id itself is readable without the key, so alert-rule registration keeps
    working; only verifying an inbound Cloudflare webhook needs the secret."""

    code = ErrorCode.WEBHOOK_SECRET_UNREADABLE
    message = "Stored Cloudflare webhook secret cannot be decrypted with the current key"
