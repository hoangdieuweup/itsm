"""List a project's roles, enriched with each permission's resource/action/description."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectRoleRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacApi


class ListProjectRoles(AbstractUseCase):
    def __init__(self, uow: AbstractProjectsUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, project_id: UUID) -> list[ProjectRoleRead]:
        project = await self._uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFound()

        rows = await self._uow.project_roles.list_for_project(project_id)

        all_permission_ids = {pid for row in rows for pid in row.permission_ids}
        permissions_by_id = {
            p.id: p for p in await self._rbac_api.get_permissions_by_ids(list(all_permission_ids))
        }

        return [
            ProjectRoleRead(
                id=row.id,
                project_id=row.project_id,
                name=row.name,
                permissions=[
                    permissions_by_id[pid] for pid in row.permission_ids if pid in permissions_by_id
                ],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
