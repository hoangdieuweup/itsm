"""List a project's members, enriched with each user's email/name."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectMemberRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.users.public import UsersApi


class ListProjectMembers(AbstractUseCase):
    """Return every member row for a project, enriched with the target
    user's email/name — the repository only knows user_id; resolving a
    human-readable identity is cross-module composition, which belongs in a
    use case, never the router or the repository."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, users_api: UsersApi) -> None:
        self._uow = uow
        self._users_api = users_api

    @use_case
    async def execute(self, project_id: UUID) -> list[ProjectMemberRead]:
        project = await self._uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFound()

        rows = await self._uow.project_members.list_for_project(project_id)
        result: list[ProjectMemberRead] = []
        for row in rows:
            user = await self._users_api.get_user_by_id(row.user_id)
            if user is None:
                continue
            result.append(
                ProjectMemberRead(
                    user_id=row.user_id, email=user.email, name=user.name, created_at=row.created_at
                )
            )
        return result
