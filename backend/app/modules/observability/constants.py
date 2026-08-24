from enum import StrEnum


class LokiAuthType(StrEnum):
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"


class ObservabilityLimits:
    MAX_ENDPOINT_URL_LENGTH = 2048
    MAX_TENANT_ID_LENGTH = 128
    MAX_QUERY_LENGTH = 4096
    MAX_QUERY_LIMIT = 1000
    DEFAULT_QUERY_LIMIT = 200


class ErrorCode(StrEnum):
    CONFIG_NOT_FOUND = "loki_config_not_found"
    CONFIG_ALREADY_EXISTS = "loki_config_already_exists"
    ENVIRONMENT_NOT_FOUND = "observability_environment_not_found"
    ALERT_RULE_NOT_FOUND = "alert_rule_not_found"
    INCIDENT_NOT_FOUND = "incident_not_found"
    INVALID_INCIDENT_TRANSITION = "invalid_incident_transition"
    INVALID_WEBHOOK_SECRET = "invalid_webhook_secret"
    CLOUDFLARE_NOT_BOUND = "cloudflare_not_bound_for_alerting"
    MISSING_CF_ALERT_TYPE = "missing_cf_alert_type"


class ObservabilityAuditActions(StrEnum):
    LOKI_CONFIG_CREATED = "LOKI_CONFIG_CREATED"
    LOKI_CONFIG_UPDATED = "LOKI_CONFIG_UPDATED"
    LOKI_CONFIG_DELETED = "LOKI_CONFIG_DELETED"


class AlertRuleSource(StrEnum):
    CLOUDFLARE_NATIVE = "CLOUDFLARE_NATIVE"
    LOKI_QUERY = "LOKI_QUERY"


class IncidentSource(StrEnum):
    CLOUDFLARE = "CLOUDFLARE"
    LOKI = "LOKI"
    MANUAL = "MANUAL"


class IncidentCategory(StrEnum):
    TRAFFIC = "TRAFFIC"
    DDOS = "DDOS"
    ORIGIN_ERROR = "ORIGIN_ERROR"
    DNS_DRIFT = "DNS_DRIFT"
    TUNNEL_DRIFT = "TUNNEL_DRIFT"
    LOG_MATCH = "LOG_MATCH"
    MANUAL = "MANUAL"


class AlertSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class AlertingLimits:
    MAX_NAME_LENGTH = 255
    MAX_TITLE_LENGTH = 255
    MAX_CF_ALERT_TYPE_LENGTH = 100
    MAX_CF_POLICY_ID_LENGTH = 64
    MAX_LOG_REF_ID_LENGTH = 64
    MAX_CORRELATION_ID_LENGTH = 64


class AlertingAuditActions(StrEnum):
    ALERT_RULE_CREATED = "ALERT_RULE_CREATED"
    ALERT_RULE_UPDATED = "ALERT_RULE_UPDATED"
    ALERT_RULE_DELETED = "ALERT_RULE_DELETED"
    INCIDENT_DETECTED = "INCIDENT_DETECTED"
    INCIDENT_CREATED_MANUALLY = "INCIDENT_CREATED_MANUALLY"
    INCIDENT_ACKNOWLEDGED = "INCIDENT_ACKNOWLEDGED"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED"
    INCIDENT_NOTIFICATION_SENT = "INCIDENT_NOTIFICATION_SENT"
    DNS_DRIFT_DETECTED = "DNS_DRIFT_DETECTED"
    TUNNEL_DRIFT_DETECTED = "TUNNEL_DRIFT_DETECTED"


class CloudflareAlertTypes:
    """Known Cloudflare Notification Policy alert types."""

    ADVANCED_DDOS_L4 = "advanced_ddos_attack_l4_alert"
    ADVANCED_DDOS_L7 = "advanced_ddos_attack_l7_alert"
    HEALTH_CHECK_STATUS = "health_check_status_notification"


class CloudflareWebhookPayloadKeys:
    """Keys in Cloudflare Notification webhook payloads."""

    ALERT_EVENT = "alert_event"
    ALERT_STATE_START = "ALERT_STATE_EVENT_START"
    POLICY_ID = "policy_id"
    ALERT_CORRELATION_ID = "alert_correlation_id"
    ALERT_TYPE = "alert_type"
    TEXT = "text"


class LokiWebhookPayloadKeys:
    """Keys in Prometheus/Loki Alertmanager webhook payloads."""

    ALERTS = "alerts"
    STATUS = "status"
    STATUS_FIRING = "firing"
    LABELS = "labels"
    APP_ALERT_RULE_ID = "app_alert_rule_id"
    FINGERPRINT = "fingerprint"
    ANNOTATIONS = "annotations"
    SUMMARY = "summary"
    ALERT_NAME = "alertname"
    QUERY = "query"
    FOR = "for"
    ENDPOINT_URL = "endpoint_url"


class ObservabilityDefaults:
    """Default values across the observability module."""

    DEFAULT_RANGE_MINUTES = 60
    DEFAULT_LOKI_NAMESPACE = "itsm"
    DEFAULT_LOKI_FOR_DURATION = "5m"
    FALLBACK_CLOUDFLARE_ALERT_TITLE = "Cloudflare alert"
    FALLBACK_LOKI_ALERT_TITLE = "Loki alert"
    NOTIFICATION_STATUS_SENT = "sent"
    NOTIFICATION_STATUS_FAILED = "failed"
    SSE_EVENT_MESSAGE = "message"
    SSE_HEADER_NO_BUFFERING = "no"
    ERROR_LOKI_UNAVAILABLE = "loki_unavailable"
    AUTH_HEADER_BEARER_PREFIX = "Bearer "
    RULE_GROUP_PREFIX = "alert-rule-"


class IncidentTransitions:
    """Allowed incident status transitions."""

    ALLOWED: set[tuple[IncidentStatus, IncidentStatus]] = {
        (IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED),
        (IncidentStatus.OPEN, IncidentStatus.RESOLVED),
        (IncidentStatus.ACKNOWLEDGED, IncidentStatus.RESOLVED),
    }
