"""Settings owned by the dx_core integration.

Names follow docs/tasks/sso-login.md section 3 exactly. CLIENT_ID/CLIENT_SECRET
default to an empty string only so the settings object can be imported/tested
without a real .env; DX rejects a blank client once a real call is attempted.
POST_LOGOUT_REDIRECT_URI is optional: when empty, DxCoreClient.build_logout_url
leaves it out and DX redirects to the URI registered for this client. The key
encrypting stored DX tokens belongs to the auth module (AUTH__DX_TOKEN_FERNET_KEY).
"""

from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class DxCoreConfig(BaseSettings):
    """Environment driven settings for the WeUp DX OAuth2 client."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="DX_CORE__", extra="ignore")

    API_BASE_URL: HttpUrl = HttpUrl("https://api-dx.weupbook.com")
    CLIENT_ID: str = ""
    CLIENT_SECRET: str = ""
    SCOPES: str = ""
    POST_LOGOUT_REDIRECT_URI: str = ""


dx_core_settings = DxCoreConfig()
