"""List the permission catalog subset a project role may ever grant."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.rules import ProjectRoleRules
from app.modules.rbac.public import PermissionRead, RbacApi


class ListAssignablePermissions(AbstractUseCase):
    """Backs the project-role editor's checkbox grid WITHOUT requiring the
    global permission:read atom GET /rbac/permissions demands — a project
    admin managing only their own project's roles shouldn't need
    system-wide catalog-read access."""

    def __init__(self, rbac_api: RbacApi) -> None:
        self._rbac_api = rbac_api

    @use_case
    async def execute(self) -> list[PermissionRead]:
        catalog = await self._rbac_api.list_permission_catalog()
        assignable = ProjectRoleRules.assignable_keys()
        return [p for p in catalog if (p.resource, p.action) in assignable]
