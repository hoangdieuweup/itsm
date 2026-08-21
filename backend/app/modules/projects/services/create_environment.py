from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import EnvironmentType, ProjectAuditActions
from app.modules.projects.exceptions import EnvironmentTypeAlreadyExists, ProjectNotFound
from app.modules.projects.schemas import EnvironmentRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateEnvironment(AbstractUseCase):
    """Create an environment. Rejected if the project doesn't exist, or already
    has an environment of the requested type (UNIQUE(project_id, type))."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        project_id: UUID,
        type: EnvironmentType,
        name: str,
        base_url: str | None,
        *,
        actor_id: UUID,
        actor_email: str,
    ) -> EnvironmentRead:
        if await self._uow.projects.get_by_id(project_id) is None:
            raise ProjectNotFound()
        if await self._uow.environments.find_by_project_and_type(project_id, type) is not None:
            raise EnvironmentTypeAlreadyExists()
        env = await self._uow.environments.create(
            project_id=project_id, type=type, name=name, base_url=base_url
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.ENVIRONMENT_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Environment '{env.name}' ({env.type.value}) created",
            project_id=project_id,
            environment_id=env.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return env
