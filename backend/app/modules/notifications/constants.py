from enum import StrEnum


class NotificationChannelType(StrEnum):
    EMAIL = "email"
    BASE_VN = "base_vn"
    TELEGRAM = "telegram"
    OTHER = "other"


class NotificationsLimits:
    MAX_NAME_LENGTH = 255
    MAX_MESSAGE_TEMPLATE_LENGTH = 2000
    MAX_TEST_MESSAGE_LENGTH = 2000


class ErrorCode(StrEnum):
    CHANNEL_NOT_FOUND = "notification_channel_not_found"
    PROJECT_NOT_FOUND = "notifications_project_not_found"
    ENVIRONMENT_NOT_FOUND = "notifications_environment_not_found"
    INVALID_CONFIG = "notification_channel_invalid_config"
    UNSUPPORTED_TYPE = "notification_channel_unsupported_type"
    SMTP_NOT_CONFIGURED = "notification_smtp_not_configured"
    PERMISSION_DENIED = "notification_permission_denied"


class NotificationsAuditActions(StrEnum):
    CHANNEL_CREATED = "NOTIFICATION_CHANNEL_CREATED"
    CHANNEL_UPDATED = "NOTIFICATION_CHANNEL_UPDATED"
    CHANNEL_DELETED = "NOTIFICATION_CHANNEL_DELETED"
    TEST_SENT = "NOTIFICATION_CHANNEL_TEST_SENT"


class NotificationChannelSecrets:
    FIELDS_BY_TYPE: dict[NotificationChannelType, str] = {
        NotificationChannelType.TELEGRAM: "bot_token",
        NotificationChannelType.BASE_VN: "webhook_url",
    }


class NotificationsDefaults:
    TEST_MESSAGE = "Test notification from ITSM"
