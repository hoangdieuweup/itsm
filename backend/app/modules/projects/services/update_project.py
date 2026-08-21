from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateProject(AbstractUseCase):
    """Rename and/or redescribe a project."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        project_id: UUID,
        *,
        name: str | None,
        description: str | None,
        actor_id: UUID,
        actor_email: str,
    ) -> ProjectRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        updated = await self._uow.projects.update(project_id, name=name, description=description)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_UPDATED",
            severity=AuditSeverity.INFO,
            message=f"Project '{updated.name}' updated",
            project_id=updated.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return updated
