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


class ObservabilityAuditActions(StrEnum):
    LOKI_CONFIG_CREATED = "LOKI_CONFIG_CREATED"
    LOKI_CONFIG_UPDATED = "LOKI_CONFIG_UPDATED"
    LOKI_CONFIG_DELETED = "LOKI_CONFIG_DELETED"
