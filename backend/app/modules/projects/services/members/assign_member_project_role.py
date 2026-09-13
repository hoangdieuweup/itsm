"""Assign (or clear) a member's project-scoped role."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import ProjectRoleNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class AssignMemberProjectRole(AbstractUseCase):
    """Router gates this with require_project_permission(PROJECT_MEMBER,
    MANAGE) — project_member.manage is never project-assignable, so this
    always requires a global atom, closing the escalation loop."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        project_id: UUID,
        target_user_id: UUID,
        project_role_id: UUID | None,
        *,
        actor_id: UUID,
        actor_email: str,
    ) -> None:
        if project_role_id is not None:
            role = await self._uow.project_roles.get_by_id(project_role_id)
            if role is None or role.project_id != project_id:
                raise ProjectRoleNotFound()

        await self._uow.project_members.set_project_role(project_id, target_user_id, project_role_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.MEMBER_ROLE_ASSIGNED,
            severity=AuditSeverity.INFO,
            message=f"User {target_user_id}'s project role on {project_id} set to {project_role_id}",
            project_id=project_id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
