"""Business rules for the auth module.

Everything here is a pure decision: no I/O, no framework, no database. That is
what keeps these testable without fixtures, and it is the difference between
this class and the SSO sync/session services (out of scope for this issue),
which call these rules but also do I/O.
"""

from app.core.base.markers import rule
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import LoginPolicy, UserStatus


class AuthRules:
    """Every business decision about a user, grouped so call sites read as
    `AuthRules.can_login(...)` instead of a bare import."""

    @staticmethod
    @rule
    def can_login(status: UserStatus) -> bool:
        """Decide whether a user in this status is allowed to complete a login."""
        return status not in LoginPolicy.BLOCKED_STATUSES

    @staticmethod
    @rule
    def is_protected_admin_email(email: str) -> bool:
        """True when email matches the seeded break-glass admin account
        (AUTH__ADMIN_EMAIL) — that account can never be blocked or have its
        role reassigned, regardless of how many other admins exist."""
        return bool(auth_settings.ADMIN_EMAIL) and email == auth_settings.ADMIN_EMAIL
