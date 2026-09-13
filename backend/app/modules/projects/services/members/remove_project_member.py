"""Remove a user's membership on a project."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class RemoveProjectMember(AbstractUseCase):
    """Remove a user's membership row entirely. A no-op (not an error) when
    the target was never a member — mirrors every delete method in
    projects/repository.py. Router gates this with require_permission
    (PROJECT, UPDATE) + require_project_membership()."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, project_id: UUID, target_user_id: UUID, *, actor_id: UUID, actor_email: str
    ) -> None:
        project = await self._uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFound()

        await self._uow.project_members.remove(project_id, target_user_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.MEMBER_REMOVED,
            severity=AuditSeverity.INFO,
            message=f"User {target_user_id}'s membership on '{project.name}' removed",
            project_id=project.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
