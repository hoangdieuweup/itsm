"""Constants owned by the queue integration."""

from enum import StrEnum


class QueueDefaults:
    """Numeric defaults owned by the queue integration."""

    MAX_RETRIES = 3
    RETRY_DELAY_MS = 30000
    DEFAULT_PREFETCH = 20


class QueueErrorCode(StrEnum):
    """Stable error codes raised by this integration."""

    PUBLISH_FAILED = "queue_publish_failed"
    NOT_CONNECTED = "queue_not_connected"


class ExchangeType(StrEnum):
    """Exchange kinds this integration declares."""

    TOPIC = "topic"
    DIRECT = "direct"
