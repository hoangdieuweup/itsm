"""Settings owned by the auth module.

Splitting settings per module keeps the global config from turning into a
dumping ground and lets a module be extracted with its configuration intact.
"""

from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings


class AuthConfig(BaseSettings):
    """Environment driven settings for the auth module's own session."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUTH__", extra="ignore")

    JWT_SECRET: str = "change-me-in-env"
    ACCESS_TOKEN_TTL_SECONDS: int = 1800
    REFRESH_TOKEN_TTL_SECONDS: int = 2592000
    COOKIE_SECURE: bool = True
    ADMIN_EMAIL: str | None = None
    ADMIN_NAME: str = "Admin"

    @property
    def cookie_domain(self) -> str | None:
        """Parent domain so session cookies are shared across subdomains
        (e.g. app.example.com <-> api.example.com), per
        docs/tasks/sso-login.md section 5.3. None in local dev, where the
        browser scopes the cookie to the request's own origin instead."""
        host = urlparse(settings.FRONTEND_BASE_URL).hostname or ""
        parts = host.split(".")
        if len(parts) <= 2 or host in ("localhost", "127.0.0.1"):
            return None
        return "." + ".".join(parts[-2:])


auth_settings = AuthConfig()
