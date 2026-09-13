from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.notifications.constants import ErrorCode


class NotificationChannelNotFound(NotFoundError):
    code = ErrorCode.CHANNEL_NOT_FOUND
    message = "Notification channel not found"


class NotificationsProjectNotFound(NotFoundError):
    code = ErrorCode.PROJECT_NOT_FOUND
    message = "Project not found"


class NotificationsEnvironmentNotFound(NotFoundError):
    """Module-local on purpose — notifications defines its own rather than
    importing projects' EnvironmentNotFound, keeping cross-module coupling
    to data only (mirrors CloudflareEnvironmentNotFound's reasoning)."""

    code = ErrorCode.ENVIRONMENT_NOT_FOUND
    message = "Environment not found"


class InvalidChannelConfig(ValidationFailedError):
    code = ErrorCode.INVALID_CONFIG
    message = "This channel's config is missing required fields for its type"


class UnsupportedChannelType(ValidationFailedError):
    code = ErrorCode.UNSUPPORTED_TYPE
    message = "This channel type does not support sending yet"


class SmtpNotConfigured(ValidationFailedError):
    code = ErrorCode.SMTP_NOT_CONFIGURED
    message = "SMTP relay is not configured — set EMAIL__SMTP_HOST and related env vars"
