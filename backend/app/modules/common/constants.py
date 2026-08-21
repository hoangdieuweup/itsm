"""Common constants and shared enums across modules."""

from enum import StrEnum


class UserStatus(StrEnum):
    """Lifecycle state of a user account."""

    ACTIVE = "active"
    PENDING = "pending"
    BLOCKED = "blocked"
