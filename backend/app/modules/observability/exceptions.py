from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    SecretUnreadableError,
    ValidationFailedError,
)
from app.modules.observability.constants import ErrorCode


class LokiConfigNotFound(NotFoundError):
    """Raised when no loki_configs row exists for the requested environment."""

    code = ErrorCode.CONFIG_NOT_FOUND
    message = "Loki config not found for this environment"


class LokiConfigAlreadyExists(ConflictError):
    """Raised when an environment already has a Loki config (environment_id is UNIQUE)."""

    code = ErrorCode.CONFIG_ALREADY_EXISTS
    message = "A Loki config already exists for this environment"


class ObservabilityEnvironmentNotFound(NotFoundError):
    """Raised when the referenced environment_id does not exist. Module-local
    on purpose — observability defines its own rather than importing
    projects' EnvironmentNotFound, keeping cross-module coupling to data
    only (mirrors cloudflare's CloudflareEnvironmentNotFound)."""

    code = ErrorCode.ENVIRONMENT_NOT_FOUND
    message = "Environment not found"


class AlertRuleNotFound(NotFoundError):
    code = ErrorCode.ALERT_RULE_NOT_FOUND
    message = "Alert rule not found"


class IncidentNotFound(NotFoundError):
    code = ErrorCode.INCIDENT_NOT_FOUND
    message = "Incident not found"


class ObservabilityPermissionDenied(ForbiddenError):
    """Raised when the caller's effective project permission set (global
    UNION project role) does not include the required resource.action for
    this environment. Observability-owned rather than importing projects'
    ProjectPermissionDenied — that class isn't exported through
    projects/public.py, and cross-module error reuse would break the
    module-owns-its-errors rule (mirrors ProjectPermissionDenied's own
    docstring reasoning in the projects module)."""

    code = ErrorCode.PERMISSION_DENIED
    message = "You do not have this permission on this project"


class InvalidIncidentTransition(ValidationFailedError):
    code = ErrorCode.INVALID_INCIDENT_TRANSITION
    message = "This status change is not allowed from the incident's current state"


class InvalidWebhookSecret(ForbiddenError):
    """The one 401 in this codebase outside auth/ — mirrors auth/exceptions.py's
    NotAuthenticated, the only existing precedent for overriding status_code."""

    code = ErrorCode.INVALID_WEBHOOK_SECRET
    message = "Invalid webhook secret"
    status_code = 401


class CloudflareNotBoundForAlerting(NotFoundError):
    """Raised when a CLOUDFLARE_NATIVE alert rule is created/edited for an
    environment with no bound Cloudflare account (Phase 4's cloudflare_configs
    has no row). Distinct from ObservabilityEnvironmentNotFound — the
    environment itself exists, it just has nothing to create a Notification
    Policy against."""

    code = ErrorCode.CLOUDFLARE_NOT_BOUND
    message = "This environment has no Cloudflare account bound"


class CloudflareAccountNotFoundForAlerting(NotFoundError):
    """Raised when listing available alert types for a Cloudflare account id
    that doesn't exist or has no stored token. Distinct from
    CloudflareNotBoundForAlerting, which is about an ENVIRONMENT having no
    bound account — this route has no environment in its path at all."""

    code = ErrorCode.CLOUDFLARE_ACCOUNT_NOT_FOUND_FOR_ALERTING
    message = "Cloudflare account not found"


class MissingCloudflareAlertType(ValidationFailedError):
    """Raised when a CLOUDFLARE_NATIVE alert rule is created without
    cf_alert_type — required for that source, unlike LOKI_QUERY where it's
    genuinely unused."""

    code = ErrorCode.MISSING_CF_ALERT_TYPE
    message = "cf_alert_type is required for a Cloudflare-native alert rule"


class CloudflarePolicyNotFound(Exception):
    """Internal control-flow signal only — never raised past the webhook
    receiver's own handler; a webhook whose policy_id matches nothing logs a
    warning and returns 200, it never surfaces this as an HTTP error to
    Cloudflare."""


class LokiCredentialUnreadable(SecretUnreadableError):
    """Raised when a stored Loki credential can't be decrypted with the current
    OBSERVABILITY__FERNET_KEY — it was saved under a different key, or no valid key
    is set. An admin has to re-enter it in the environment's Loki settings."""

    code = ErrorCode.CREDENTIAL_UNREADABLE
    message = "Stored Loki credential cannot be decrypted with the current key"
