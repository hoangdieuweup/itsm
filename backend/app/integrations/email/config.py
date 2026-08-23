from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailIntegrationConfig(BaseSettings):
    """Environment driven settings for the app-wide SMTP relay. Every
    notification_channels.type=EMAIL row only stores `recipients` — the
    actual sending credentials are global, not per-channel."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="EMAIL__", extra="ignore")

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = ""
    SMTP_START_TLS: bool = True


email_settings = EmailIntegrationConfig()
