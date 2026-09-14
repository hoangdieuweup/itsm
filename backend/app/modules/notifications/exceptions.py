from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    SecretUnreadableError,
    ValidationFailedError,
)
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


class NotificationPermissionDenied(ForbiddenError):
    """Raised when the caller lacks a project-scoped notification permission."""

    code = ErrorCode.PERMISSION_DENIED
    message = "Missing permission"


class NotificationChannelSecretUnreadable(SecretUnreadableError):
    """Raised when a channel's stored secret (Telegram bot token, Base.vn webhook URL)
    can't be decrypted with the current NOTIFICATIONS__FERNET_KEY. An admin has to
    re-enter it on the channel."""

    code = ErrorCode.SECRET_UNREADABLE
    message = "Stored notification channel secret cannot be decrypted with the current key"
