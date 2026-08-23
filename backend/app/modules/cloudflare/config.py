"""Settings owned by the cloudflare module — the business-domain secret only.
HTTP transport settings (API_BASE_URL, HTTP_TIMEOUT_SECONDS) live in
app.integrations.cloudflare.config instead, since they're a transport
concern, not a domain one."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class CloudflareConfig(BaseSettings):
    """Environment driven settings for the cloudflare module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CLOUDFLARE__", extra="ignore")

    # Fernet key encrypting CloudflareAccount.api_token at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""


cloudflare_settings = CloudflareConfig()
