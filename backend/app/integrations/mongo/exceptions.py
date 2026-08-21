"""Errors owned by the mongo integration."""

from app.core.exceptions import IntegrationError
from app.integrations.mongo.constants import MongoErrorCode


class MongoUnavailable(IntegrationError):
    """Raised when MongoDB cannot be reached for an operation that cannot degrade silently."""

    code = MongoErrorCode.UNAVAILABLE
    message = "Log store unavailable"
