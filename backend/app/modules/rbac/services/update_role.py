"""Use case: rename a role and/or replace its permission set."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.constants import RbacCacheKeys
from app.modules.rbac.exceptions import RoleNotFound, SystemRoleImmutable, UnknownPermissionId
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import RoleRead
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class UpdateRole(AbstractUseCase):
    """A system role's permissions stay editable even though its name is locked
    (RbacRules.can_rename_role) — see spec's role.update note."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, role_id: int, *, name: str | None, permission_ids: list[int] | None) -> RoleRead:
        role = await self._uow.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound()
        if name is not None and not RbacRules.can_rename_role(role):
            raise SystemRoleImmutable()
        if permission_ids is not None:
            found = await self._uow.permissions.find_by_ids(permission_ids)
            if len(found) != len(set(permission_ids)):
                raise UnknownPermissionId()
        updated = await self._uow.roles.update(role_id, name=name, permission_ids=permission_ids)
        self._uow.mark_stale(RbacCacheKeys.ROLE_ENTITY, role_id)
        await self._uow.commit()
        return updated
