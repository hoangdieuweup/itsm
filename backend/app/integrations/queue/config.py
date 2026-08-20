"""Settings owned by the queue integration."""

from pydantic import AmqpDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.integrations.queue.constants import QueueDefaults


class QueueConfig(BaseSettings):
    """Environment driven settings for RabbitMQ."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="QUEUE_", extra="ignore")

    URL: AmqpDsn = "amqp://guest:guest@localhost:5672/"
    PREFETCH: int = QueueDefaults.DEFAULT_PREFETCH
    MAX_RETRIES: int = QueueDefaults.MAX_RETRIES
    PUBLISHER_CONFIRMS: bool = True


queue_settings = QueueConfig()
