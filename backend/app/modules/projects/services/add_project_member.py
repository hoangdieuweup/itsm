"""Add a user as a member of a project."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import ProjectMemberAlreadyExists, ProjectNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class AddProjectMember(AbstractUseCase):
    """Grant a user membership on a project. Router gates this with
    require_permission(PROJECT, UPDATE) + require_project_membership() —
    only an existing member (or a manage_all holder) can add someone else."""

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

        if await self._uow.project_members.is_member(project_id, target_user_id):
            raise ProjectMemberAlreadyExists()

        await self._uow.project_members.add(project_id, target_user_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.MEMBER_ADDED,
            severity=AuditSeverity.INFO,
            message=f"User {target_user_id} added as a member of '{project.name}'",
            project_id=project.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
