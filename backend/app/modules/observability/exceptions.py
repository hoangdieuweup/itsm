from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
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


class InvalidIncidentTransition(ValidationFailedError):
    code = ErrorCode.INVALID_INCIDENT_TRANSITION
    message = "This status change is not allowed from the incident's current state"


class InvalidWebhookSecret(ForbiddenError):
    """The one 401 in this codebase outside auth/ — mirrors auth/exceptions.py's
    NotAuthenticated, the only existing precedent for overriding status_code."""

    code = ErrorCode.INVALID_WEBHOOK_SECRET
    message = "Invalid webhook secret"
    status_code = 401


class CloudflarePolicyNotFound(Exception):
    """Internal control-flow signal only — never raised past the webhook
    receiver's own handler; a webhook whose policy_id matches nothing logs a
    warning and returns 200, it never surfaces this as an HTTP error to
    Cloudflare."""
