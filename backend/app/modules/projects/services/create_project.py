from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.rules import ProjectsRules
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateProject(AbstractUseCase):
    """Create a project, then attach the configured default Jira/Git links
    (ProjectsRules.default_links) — see spec's project_links note: these are
    seeded values, not a template table, so nothing here is admin-editable."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, name: str, description: str | None, *, actor_id: UUID, actor_email: str
    ) -> ProjectRead:
        project = await self._uow.projects.create(name=name, description=description, created_by=None)
        for link_type, link_name, url in ProjectsRules.default_links():
            await self._uow.project_links.create(
                project_id=project.id, type=link_type, name=link_name, url=url, is_default=True
            )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_CREATED",
            severity=AuditSeverity.INFO,
            message=f"Project '{project.name}' created",
            project_id=project.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return project
