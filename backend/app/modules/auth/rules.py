"""Business rules for the auth module.

Everything here is a pure decision: no I/O, no framework, no database. That is
what keeps these testable without fixtures, and it is the difference between
this class and the SSO sync/session services (out of scope for this issue),
which call these rules but also do I/O.
"""

from app.core.base.markers import rule
from app.modules.auth.constants import LoginPolicy
from app.modules.users.public import UserStatus


class AuthRules:
    """Every business decision about a user, grouped so call sites read as
    `AuthRules.can_login(...)` instead of a bare import."""

    @staticmethod
    @rule
    def can_login(status: UserStatus) -> bool:
        """Decide whether a user in this status is allowed to complete a login."""
        return status not in LoginPolicy.BLOCKED_STATUSES
