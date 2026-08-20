"""Constants owned by the cache integration."""

from enum import StrEnum


class CacheDefaults:
    """Numeric defaults owned by the cache integration."""

    VERSION_TTL_SECONDS = 86400
    DEFAULT_TTL_SECONDS = 300
    PAYLOAD_SCHEMA_VERSION = 1


class CacheErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UNAVAILABLE = "cache_unavailable"
    SERIALIZATION_FAILED = "cache_serialization_failed"
