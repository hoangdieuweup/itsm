from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramIntegrationConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TELEGRAM__", extra="ignore")

    API_BASE_URL: HttpUrl = HttpUrl("https://api.telegram.org")
    HTTP_TIMEOUT_SECONDS: float = 10.0


telegram_settings = TelegramIntegrationConfig()
