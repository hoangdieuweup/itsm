from enum import StrEnum


class EmailErrorCode(StrEnum):
    UNAVAILABLE = "email_unavailable"
    INVALID_CREDENTIAL = "email_invalid_credential"
    REJECTED = "email_rejected"
