"""Settings owned by the loki integration — transport only. Unlike Cloudflare's
single shared API_BASE_URL, every environment can point at a different Loki
cluster (loki_configs.endpoint_url is a per-row column), so there is no
base-URL setting here — callers pass endpoint_url per call."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class LokiIntegrationConfig(BaseSettings):
    """Environment driven settings for the Loki HTTP client."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LOKI__", extra="ignore")

    HTTP_TIMEOUT_SECONDS: float = 10.0


loki_settings = LokiIntegrationConfig()
