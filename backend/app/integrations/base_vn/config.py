from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseVnIntegrationConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BASE_VN__", extra="ignore")

    HTTP_TIMEOUT_SECONDS: float = 10.0


base_vn_settings = BaseVnIntegrationConfig()
