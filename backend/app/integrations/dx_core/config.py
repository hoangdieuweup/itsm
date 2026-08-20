"""Settings owned by the dx_core integration.

Names follow docs/tasks/sso-login.md section 3 exactly. CLIENT_ID/CLIENT_SECRET/
FERNET_KEY default to an empty string only so the settings object can be
imported/tested without a real .env — DxCoreClient/DxTokenRepository fail
fast (see their own docstrings) rather than silently proceeding once a real
call is attempted with a blank value.
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
    # Fernet key encrypting DxToken.access_token/refresh_token at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""


dx_core_settings = DxCoreConfig()
