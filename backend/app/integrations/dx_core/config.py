"""Settings owned by the dx_core integration.

Names follow docs/tasks/sso-login.md section 3 exactly. CLIENT_ID/CLIENT_SECRET
default to an empty string only so the settings object can be imported/tested
without a real .env; the client stubs below never call the real DX API in this
issue's scope, so no code path yet depends on these being non-empty in a real
environment. A future run wiring the real OAuth flow must fail fast instead of
silently proceeding when either is blank.
"""

from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class DxCoreConfig(BaseSettings):
    """Environment driven settings for the WeUpBook DX OAuth2 client."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="WEUPBOOK_", extra="ignore")

    API_BASE_URL: HttpUrl = HttpUrl("https://api-dx.weupbook.com")
    CLIENT_ID: str = ""
    CLIENT_SECRET: str = ""
    SCOPES: str = ""


dx_core_settings = DxCoreConfig()
