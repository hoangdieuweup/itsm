from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.telegram.constants import TelegramErrorCode


class TelegramApiUnavailable(IntegrationError):
    code = TelegramErrorCode.UNAVAILABLE
    message = "Telegram Bot API unavailable"


class InvalidTelegramCredential(ValidationFailedError):
    code = TelegramErrorCode.INVALID_CREDENTIAL
    message = "Telegram rejected the provided bot token"


class TelegramRejected(ValidationFailedError):
    code = TelegramErrorCode.REJECTED
    message = "Telegram rejected this message"
