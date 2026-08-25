"""Rename and/or re-permission a project role."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import PermissionNotProjectAssignable, ProjectRoleNotFound
from app.modules.projects.rules import ProjectRoleRules
from app.modules.projects.schemas import ProjectRoleRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacApi


class UpdateProjectRole(AbstractUseCase):
    """Router gates this with require_project_permission(PROJECT_ROLE, MANAGE)."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, rbac_api: RbacApi, audit_api: AuditApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        project_role_id: UUID,
        *,
        name: str | None,
        permission_ids: list[UUID] | None,
        actor_id: UUID,
        actor_email: str,
    ) -> ProjectRoleRead:
        existing = await self._uow.project_roles.get_by_id(project_role_id)
        if existing is None:
            raise ProjectRoleNotFound()

        if permission_ids is not None:
            permissions = await self._rbac_api.get_permissions_by_ids(permission_ids)
            rejected = ProjectRoleRules.rejects_unassignable([(p.resource, p.action) for p in permissions])
            if rejected:
                raise PermissionNotProjectAssignable()

        row = await self._uow.project_roles.update(project_role_id, name=name, permission_ids=permission_ids)
        await self._uow.commit()

        all_permissions = await self._rbac_api.get_permissions_by_ids(row.permission_ids)
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.PROJECT_ROLE_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Project role '{row.name}' updated",
            project_id=row.project_id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return ProjectRoleRead(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            permissions=all_permissions,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
