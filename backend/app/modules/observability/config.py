"""Settings owned by the observability module — the business-domain secret
only. Mirrors app/modules/cloudflare/config.py's exact split (domain secret
in the module, transport settings in the integration)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilityConfig(BaseSettings):
    """Environment driven settings for the observability module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="OBSERVABILITY__", extra="ignore")

    # Fernet key encrypting LokiConfig.credential at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""


observability_settings = ObservabilityConfig()
