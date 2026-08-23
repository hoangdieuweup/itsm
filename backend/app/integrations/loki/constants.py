from enum import StrEnum


class LokiErrorCode(StrEnum):
    UNAVAILABLE = "loki_unavailable"
    INVALID_CREDENTIAL = "loki_invalid_credential"
    QUERY_REJECTED = "loki_query_rejected"
