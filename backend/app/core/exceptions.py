"""Error mechanism shared by every module.

Concrete errors such as UserNotFound belong to the module that owns the concept.
Only the base classes and the HTTP mapping live here.
"""

from typing import Any


class AppError(Exception):
    """Base error carrying a stable machine readable code and optional context."""

    code = "app_error"
    status_code = 400
    message = "Application error"

    def __init__(self, message: str | None = None, **context: Any) -> None:
        self.message = message or self.message
        self.context = context
        super().__init__(self.message)


class NotFoundError(AppError):
    """Base for every missing resource error."""

    code = "not_found"
    status_code = 404
    message = "Resource not found"


class ConflictError(AppError):
    """Base for every uniqueness or state conflict."""

    code = "conflict"
    status_code = 409
    message = "Conflicting state"


class ForbiddenError(AppError):
    """Base for every permission failure."""

    code = "forbidden"
    status_code = 403
    message = "Not permitted"


class ValidationFailedError(AppError):
    """Base for input that is well formed but violates a business rule."""

    code = "validation_failed"
    status_code = 422
    message = "Validation failed"


class IntegrationError(AppError):
    """Base for failures originating in an external system."""

    code = "integration_error"
    status_code = 502
    message = "Upstream integration failed"
