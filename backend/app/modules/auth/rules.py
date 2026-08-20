"""Business rules for the auth module.

Everything here is a pure decision: no I/O, no framework, no database. That is
what keeps these testable without fixtures, and it is the difference between
this class and the SSO sync/session services (out of scope for this issue),
which call these rules but also do I/O.
"""

from app.core.base.markers import rule
from app.modules.auth.constants import LoginPolicy, RoleMapping, UserRole, UserStatus


class AuthRules:
    """Every business decision about a user, grouped so call sites read as
    `AuthRules.can_login(...)` instead of a bare import."""

    @staticmethod
    @rule
    def resolve_role(external_role_code: str | None) -> UserRole:
        """Map a DX external role code to an application role.

        Unknown or missing codes fall back to RoleMapping.DEFAULT_EXTERNAL_ROLE_CODE
        (the least privileged role) rather than raising, since DX is the
        source of truth for who exists but this app decides what "employee"
        means here.
        """
        code = external_role_code or RoleMapping.DEFAULT_EXTERNAL_ROLE_CODE
        return RoleMapping.EXTERNAL_ROLE_MAP.get(
            code, RoleMapping.EXTERNAL_ROLE_MAP[RoleMapping.DEFAULT_EXTERNAL_ROLE_CODE]
        )

    @staticmethod
    @rule
    def can_login(status: UserStatus) -> bool:
        """Decide whether a user in this status is allowed to complete a login."""
        return status not in LoginPolicy.BLOCKED_STATUSES
