"""Constants and enums owned by the audit module."""

from enum import StrEnum


class AuditCollections:
    """Mongo collection names owned by this module."""

    LOGS = "logs"


class AuditEventType(StrEnum):
    """What kind of event a log entry records."""

    AUDIT = "AUDIT"
    INCIDENT_DETECTION = "INCIDENT_DETECTION"
    NOTIFICATION_SENT = "NOTIFICATION_SENT"


class AuditSource(StrEnum):
    """Which system produced the event."""

    CLOUDFLARE = "CLOUDFLARE"
    LOKI = "LOKI"
    SYSTEM = "SYSTEM"
    USER_ACTION = "USER_ACTION"


class AuditSeverity(StrEnum):
    """Severity of a log entry."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AuditLimits:
    """Numeric limits owned by the audit module."""

    DEFAULT_PAGE_SIZE = 50


class AuditRetention:
    """TTL retention windows, per spec section 4 — AUDIT is shorter lived than
    incident/notification history. Applied via a per-document `expire_at`
    field (not a fixed TTL on created_at) since Mongo TTL indexes apply one
    duration per field, not per document value."""

    AUDIT_TTL_DAYS = 180
    OTHER_TTL_DAYS = 365
