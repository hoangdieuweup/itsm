"""Events published by the auth module."""

from app.auth.constants import AuthEvents
from app.events import DomainEvent


class UserCreated(DomainEvent):
    """Emitted after a new user has been synced from DX for the first time."""

    user_id: int
    email: str

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event."""
        return f"{AuthEvents.EXCHANGE}.user_created"


class UserLoggedIn(DomainEvent):
    """Emitted after a user completes the SSO login flow."""

    user_id: int

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event."""
        return f"{AuthEvents.EXCHANGE}.user_logged_in"
