from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.base_vn.constants import BaseVnErrorCode


class BaseVnApiUnavailable(IntegrationError):
    code = BaseVnErrorCode.UNAVAILABLE
    message = "Base.vn webhook unavailable"


class BaseVnRejected(ValidationFailedError):
    """No credential concept for a bearer-in-URL webhook — every non-2xx
    that isn't a transport/5xx failure means the webhook itself declined
    the payload."""

    code = BaseVnErrorCode.REJECTED
    message = "Base.vn webhook rejected this message"
