"""Settings owned by the cloudflare module."""

from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class CloudflareConfig(BaseSettings):
    """Environment driven settings for the cloudflare module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CLOUDFLARE__", extra="ignore")

    API_BASE_URL: HttpUrl = HttpUrl("https://api.cloudflare.com/client/v4")
    # Fernet key encrypting CloudflareAccount.api_token at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""
    HTTP_TIMEOUT_SECONDS: float = 10.0


cloudflare_settings = CloudflareConfig()
