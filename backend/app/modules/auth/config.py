"""Settings owned by the auth module.

Splitting settings per module keeps the global config from turning into a
dumping ground and lets a module be extracted with its configuration intact.
Only the shape of the settings is scaffolded here — nothing reads JWT_SECRET
or FERNET_KEY yet; that happens once app/core/security.py and
app/core/crypto.py are implemented (out of scope for this issue).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthConfig(BaseSettings):
    """Environment driven settings for the auth module's own session."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUTH_", extra="ignore")

    JWT_SECRET: str = "change-me-in-env"
    ACCESS_TOKEN_TTL_SECONDS: int = 1800
    REFRESH_TOKEN_TTL_SECONDS: int = 2592000
    COOKIE_SECURE: bool = True


auth_settings = AuthConfig()
