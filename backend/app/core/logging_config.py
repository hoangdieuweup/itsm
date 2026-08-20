"""Structured logging.

One JSON shape whether a log line comes from structlog or the standard
library, with request context (and trace context, when tracing is enabled)
merged in automatically instead of passed by hand at every call site.
"""

import logging
import sys

import structlog

from app.config import settings
from app.constants import LogLevel

SENSITIVE_KEYS = {"password", "token", "authorization", "secret", "api_key", "credit_card"}


def _redact_sensitive(logger, method_name, event_dict):
    """Mask values behind keys that should never reach a log sink."""
    for key in event_dict:
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict


SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    _redact_sensitive,
]


def setup_logging() -> None:
    """Route structlog and stdlib logging through one formatter and level."""
    structlog.configure(
        processors=[*SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = (
        structlog.dev.ConsoleRenderer(colors=True)
        if settings.ENV.is_debug
        else structlog.processors.JSONRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=SHARED_PROCESSORS,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(LogLevel.DEBUG if settings.ENV.is_debug else settings.LOG_LEVEL)
