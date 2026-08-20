"""Project wide constants. Business constants belong to their own module."""

from enum import StrEnum


class Environment(StrEnum):
    """Deployment environment the process is running in."""

    DEV = "dev"
    STAGING = "stg"
    PRODUCTION = "prod"

    @property
    def is_debug(self) -> bool:
        """Return whether debug level logging is enabled in this environment."""
        return self is self.DEV


class LogLevel(StrEnum):
    """Valid values for LOG_LEVEL. A closed set, not a free string."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
