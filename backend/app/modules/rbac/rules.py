"""Business rules for the rbac module. Pure decisions: no I/O, no framework."""

from app.core.base.markers import rule
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.schemas import RoleRead


class RbacRules:
    """Every business decision about a role or a role grant."""

    @staticmethod
    @rule
    def can_delete_role(role: RoleRead) -> bool:
        """A system-seeded role (admin/member) can never be deleted."""
        return not role.is_system

    @staticmethod
    @rule
    def can_rename_role(role: RoleRead) -> bool:
        """A system-seeded role's name is fixed; its permission set is still editable."""
        return not role.is_system

    @staticmethod
    @rule
    def blocks_last_admin_removal(role_name: str, remaining_admin_grants: int) -> bool:
        """True when reassigning/blocking this grant would leave zero users able to
        manage roles or users. remaining_admin_grants counts admin-role holders
        *including* the one about to be changed."""
        return role_name == RbacDefaults.ADMIN_ROLE_NAME and remaining_admin_grants <= 1
