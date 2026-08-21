"""Use case: grant the seeded default role to a newly synced user."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class AssignDefaultRole(AbstractUseCase):
    """Called by auth's AuthenticateWithDx right after a brand new user is created —
    replaces the old DX-role-code auto-mapping (RoleMapping/resolve_role, removed)."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, user_id: int) -> None:
        role = await self._uow.roles.find_by_name(RbacDefaults.DEFAULT_ROLE_NAME)
        if role is None:
            raise RuntimeError(
                f"seed role {RbacDefaults.DEFAULT_ROLE_NAME!r} missing — run `python -m app.seeds.seed_rbac`"
            )
        await self._uow.user_roles.assign(user_id, role.id)
        # No mark_stale() here: this uow's own commit() never runs (auth's
        # uow commits this same DB transaction instead — see below), so
        # anything queued here would never flush. Safe to skip: this only
        # ever runs for a brand-new user_id, so no user_role:{user_id} cache
        # entry could exist yet to invalidate.
        # deliberately no commit() here — see Task 11: this runs inside
        # AuthenticateWithDx's transaction and is committed by auth's own uow.commit()
