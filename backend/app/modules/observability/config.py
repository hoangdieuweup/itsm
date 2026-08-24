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

    # App-wide shared secret Alertmanager's http_config.authorization sends as
    # a bearer token — compared directly, never decrypted, so a plain string
    # setting is correct here (not a ciphertext-in-DB pattern like FERNET_KEY).
    LOKI_WEBHOOK_SECRET: str = ""

    # How often the drift reconciliation job (app/scheduler.py) re-checks
    # every Cloudflare-bound environment's DNS/Tunnel state. Within the
    # spec's own stated 15-30 minute window.
    RECONCILIATION_INTERVAL_SECONDS: int = 1200


observability_settings = ObservabilityConfig()
