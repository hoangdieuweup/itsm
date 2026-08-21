"""Business rules for the users module.

Everything here is a pure decision: no I/O, no framework, no database.
"""

from app.core.base.markers import rule
from app.modules.users.config import users_settings


class UsersRules:
    """Every business decision about a user account."""

    @staticmethod
    @rule
    def is_protected_admin_email(email: str) -> bool:
        """True when email matches the seeded break-glass admin account
        (USERS__ADMIN_EMAIL) — that account can never be blocked or have its
        role reassigned, regardless of how many other admins exist."""
        return bool(users_settings.ADMIN_EMAIL) and email == users_settings.ADMIN_EMAIL
