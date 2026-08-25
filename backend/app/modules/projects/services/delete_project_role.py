"""Delete a project role. Members holding it degrade to global-only (ON DELETE SET NULL)."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import ProjectRoleNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteProjectRole(AbstractUseCase):
    """Router gates this with require_project_permission(PROJECT_ROLE, MANAGE)."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, project_role_id: UUID, *, actor_id: UUID, actor_email: str) -> None:
        existing = await self._uow.project_roles.get_by_id(project_role_id)
        if existing is None:
            raise ProjectRoleNotFound()

        await self._uow.project_roles.delete(project_role_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.PROJECT_ROLE_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Project role '{existing.name}' deleted",
            project_id=existing.project_id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
