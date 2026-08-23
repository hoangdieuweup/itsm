from pydantic_settings import BaseSettings, SettingsConfigDict


class NotificationsConfig(BaseSettings):
    """Environment driven settings for the notifications module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NOTIFICATIONS__", extra="ignore")

    # Fernet key encrypting NotificationChannel.config's secret sub-fields
    # (TELEGRAM.bot_token, BASE_VN.webhook_url) at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""


notifications_settings = NotificationsConfig()
