"""List projects visible to the current user."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacActions, RbacApi, RbacResources


class ListVisibleProjects(AbstractUseCase):
    """Return the projects the current user can see: a real paginated page of
    everything if they hold project:manage_all, otherwise every project
    where they have a project_members row, unpaginated (same accepted
    trade-off as ListVisibleCloudflareAccounts — the member-scoped set stays
    small for a single user). A user with neither gets an empty list, not a
    403 — Layer 1's `read` permission already gated reaching this use case."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, user_id: UUID, limit: int, offset: int) -> tuple[list[ProjectRead], int]:
        if await self._rbac_api.has_permission(user_id, RbacResources.PROJECT, RbacActions.MANAGE_ALL):
            return await self._uow.projects.list_page(limit, offset)

        project_ids = await self._uow.project_members.list_project_ids_for_user(user_id)
        items = await self._uow.projects.list_for_ids(project_ids)
        return items, len(items)
