"""Create a role scoped to one project."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import (
    DuplicateProjectRoleName,
    PermissionNotProjectAssignable,
    ProjectNotFound,
)
from app.modules.projects.rules import ProjectRoleRules
from app.modules.projects.schemas import ProjectRoleRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacApi


class CreateProjectRole(AbstractUseCase):
    """Create a project role. Router gates this with require_project_permission
    (PROJECT_ROLE, MANAGE) — project_role.manage is never itself project-
    assignable, so this always requires a global atom."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, rbac_api: RbacApi, audit_api: AuditApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, project_id: UUID, name: str, permission_ids: list[UUID], *, actor_id: UUID, actor_email: str
    ) -> ProjectRoleRead:
        project = await self._uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFound()

        existing = await self._uow.project_roles.find_by_name(project_id, name)
        if existing is not None:
            raise DuplicateProjectRoleName()

        permissions = await self._rbac_api.get_permissions_by_ids(permission_ids)
        rejected = ProjectRoleRules.rejects_unassignable([(p.resource, p.action) for p in permissions])
        if rejected:
            raise PermissionNotProjectAssignable()

        row = await self._uow.project_roles.create(
            project_id=project_id, name=name, permission_ids=permission_ids
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.PROJECT_ROLE_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Project role '{name}' created on '{project.name}'",
            project_id=project.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return ProjectRoleRead(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            permissions=permissions,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
