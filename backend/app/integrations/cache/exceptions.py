"""Errors owned by the cache integration."""

from app.exceptions import IntegrationError
from app.integrations.cache.constants import CacheErrorCode


class CacheUnavailable(IntegrationError):
    """Raised when Redis cannot be reached and no fallback is possible."""

    code = CacheErrorCode.UNAVAILABLE
    message = "Cache backend unavailable"
