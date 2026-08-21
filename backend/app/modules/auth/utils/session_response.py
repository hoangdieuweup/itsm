"""HTTP response shaping for the auth module's session lifecycle.

Owned here rather than in router.py so the router stays a pure HTTP-to-use-case
translator (fastapi-modular-scaffold rule #10) — see docs/tasks/sso-login.md
sections 5.5 and 11 for the cookie/redirect contract these implement.
"""

from fastapi import Response, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core.base.markers import helper
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.auth.services.issue_tokens import AppTokenSet


class AuthSessionResponses:
    """Shapes the HTTP side effects of a login/logout attempt: cookies and redirects."""

    LOGIN_PATH = "/login"

    @staticmethod
    @helper
    def login_error_redirect(error: str) -> RedirectResponse:
        """Send the browser back to the SPA's login page with a stable error code
        for it to translate — see docs/tasks/sso-login.md section 11."""
        url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}{AuthSessionResponses.LOGIN_PATH}?error={error}"
        return RedirectResponse(url, status_code=status.HTTP_302_FOUND)

    @staticmethod
    @helper
    def set_session_cookies(response: Response, tokens: AppTokenSet) -> None:
        """Set this app's own session as two HttpOnly cookies (docs section 5.5)."""
        samesite: AuthCookies.SameSite = "none" if auth_settings.COOKIE_SECURE else "lax"
        common = {
            "httponly": True,
            "samesite": samesite,
            "secure": auth_settings.COOKIE_SECURE,
            "path": "/",
            "domain": auth_settings.cookie_domain,
        }
        response.set_cookie(
            AuthCookies.ACCESS_TOKEN,
            tokens.access_token,
            max_age=auth_settings.ACCESS_TOKEN_TTL_SECONDS,
            **common,
        )
        response.set_cookie(
            AuthCookies.REFRESH_TOKEN,
            tokens.refresh_token,
            max_age=auth_settings.REFRESH_TOKEN_TTL_SECONDS,
            **common,
        )

    @staticmethod
    @helper
    def clear_session_cookies(response: Response) -> None:
        """Delete both session cookies on logout."""
        response.delete_cookie(AuthCookies.ACCESS_TOKEN, path="/", domain=auth_settings.cookie_domain)
        response.delete_cookie(AuthCookies.REFRESH_TOKEN, path="/", domain=auth_settings.cookie_domain)
