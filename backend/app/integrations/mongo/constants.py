"""Constants owned by the mongo integration."""

from enum import StrEnum


class MongoErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    UNAVAILABLE = "mongo_unavailable"
