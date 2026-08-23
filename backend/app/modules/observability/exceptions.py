from app.core.exceptions import ConflictError, NotFoundError
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
