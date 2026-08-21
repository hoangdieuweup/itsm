"""Events published by the users module."""

from app.core.events import DomainEvent
from app.modules.users.constants import UsersEvents


class UserCreated(DomainEvent):
    """Emitted after a new user has been synced from DX for the first time."""

    user_id: int
    email: str

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event."""
        return f"{UsersEvents.EXCHANGE}.user_created"
