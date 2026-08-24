from enum import StrEnum


class TelegramErrorCode(StrEnum):
    UNAVAILABLE = "telegram_unavailable"
    INVALID_CREDENTIAL = "telegram_invalid_credential"
    REJECTED = "telegram_rejected"
