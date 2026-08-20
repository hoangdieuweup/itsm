"""Errors owned by the queue integration."""

from app.core.exceptions import IntegrationError
from app.integrations.queue.constants import QueueErrorCode


class PublishFailed(IntegrationError):
    """Raised when the broker did not confirm a published message."""

    code = QueueErrorCode.PUBLISH_FAILED
    message = "Failed to publish message"


class BrokerNotConnected(IntegrationError):
    """Raised when a publish is attempted before the connection is open."""

    code = QueueErrorCode.NOT_CONNECTED
    message = "Broker connection not established"
