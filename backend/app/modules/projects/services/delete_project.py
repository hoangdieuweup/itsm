from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteProject(AbstractUseCase):
    """Delete a project. Its environments and links cascade at the DB level (ondelete=CASCADE)."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, project_id: UUID, *, actor_id: UUID, actor_email: str) -> None:
        project = await self._uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFound()
        await self._uow.projects.delete(project_id)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_DELETED",
            severity=AuditSeverity.MEDIUM,
            message=f"Project '{project.name}' deleted",
            project_id=project_id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
