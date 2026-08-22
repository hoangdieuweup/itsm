"""Settings owned by the cloudflare integration — pure HTTP transport, no
secrets (Fernet key for CloudflareAccount.api_token stays in
app.modules.cloudflare.config, since encrypting a business row's secret is a
domain concern, not a transport one)."""

from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class CloudflareConfig(BaseSettings):
    """Environment driven settings for the Cloudflare REST API v4 client."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CLOUDFLARE__", extra="ignore")

    API_BASE_URL: HttpUrl = HttpUrl("https://api.cloudflare.com/client/v4")
    HTTP_TIMEOUT_SECONDS: float = 10.0


cloudflare_settings = CloudflareConfig()
