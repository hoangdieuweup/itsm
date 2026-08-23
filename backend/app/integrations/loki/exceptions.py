"""Errors owned by the loki integration — transport/protocol failures only.
Domain-level errors (LokiConfigNotFound, etc.) live in
app.modules.observability.exceptions instead."""

from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.loki.constants import LokiErrorCode


class LokiApiUnavailable(IntegrationError):
    """Raised when the Loki API cannot be reached or returns a server error."""

    code = LokiErrorCode.UNAVAILABLE
    message = "Loki API unavailable"


class InvalidLokiCredential(ValidationFailedError):
    """Raised when Loki rejects the provided credential (401/403)."""

    code = LokiErrorCode.INVALID_CREDENTIAL
    message = "Loki rejected the provided credential"


class LokiQueryRejected(ValidationFailedError):
    """Raised when Loki rejects the query itself (malformed LogQL, etc.) —
    distinct from InvalidLokiCredential, which is specifically about auth.
    Carries Loki's own error message so a bad-syntax query reaches the user
    as a specific, actionable string."""

    code = LokiErrorCode.QUERY_REJECTED
    message = "Loki rejected this query"
