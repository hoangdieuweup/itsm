from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.email.constants import EmailErrorCode


class EmailApiUnavailable(IntegrationError):
    code = EmailErrorCode.UNAVAILABLE
    message = "SMTP relay unavailable"


class InvalidEmailCredential(ValidationFailedError):
    code = EmailErrorCode.INVALID_CREDENTIAL
    message = "SMTP relay rejected the configured credentials"


class EmailRejected(ValidationFailedError):
    code = EmailErrorCode.REJECTED
    message = "SMTP relay rejected this message"
