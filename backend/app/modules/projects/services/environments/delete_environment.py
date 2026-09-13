from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import EnvironmentNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteEnvironment(AbstractUseCase):
    """Delete an environment."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, *, actor_id: UUID, actor_email: str) -> None:
        existing = await self._uow.environments.get_by_id(environment_id)
        if existing is None:
            raise EnvironmentNotFound()
        await self._uow.environments.delete(environment_id)
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.ENVIRONMENT_DELETED,
            severity=AuditSeverity.MEDIUM,
            message=f"Environment '{existing.name}' deleted",
            project_id=existing.project_id,
            environment_id=environment_id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
