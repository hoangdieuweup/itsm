"""Mechanism shared by every module. No business logic lives here."""

from app.core.database import Base, get_session
from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationFailedError,
)
from app.core.models import ApiResponse, CustomModel, ErrorPayload, FrozenModel

__all__ = [
    "ApiResponse",
    "AppError",
    "Base",
    "ConflictError",
    "CustomModel",
    "ErrorPayload",
    "ForbiddenError",
    "FrozenModel",
    "IntegrationError",
    "NotFoundError",
    "ValidationFailedError",
    "get_session",
]
