"""Errors owned by the dx_core integration."""

from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.dx_core.constants import DxErrorCode


class DxCoreUnavailable(IntegrationError):
    """Raised when the DX OAuth2 server cannot be reached or returns a server error."""

    code = DxErrorCode.UNAVAILABLE
    message = "DX core service unavailable"


class InvalidOAuthState(ValidationFailedError):
    """Raised when the callback's state does not match a pending PKCE exchange."""

    code = DxErrorCode.INVALID_STATE
    message = "Invalid or expired OAuth state"


class TokenExchangeFailed(IntegrationError):
    """Raised when DX rejects the authorization code or PKCE verifier."""

    code = DxErrorCode.TOKEN_EXCHANGE_FAILED
    message = "Failed to exchange authorization code for tokens"
