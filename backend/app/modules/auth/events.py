"""Events published by the auth module."""

from app.core.events import DomainEvent
from app.modules.auth.constants import AuthEvents


class UserLoggedIn(DomainEvent):
    """Emitted after a user completes the SSO login flow."""

    user_id: int

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event."""
        return f"{AuthEvents.EXCHANGE}.user_logged_in"
