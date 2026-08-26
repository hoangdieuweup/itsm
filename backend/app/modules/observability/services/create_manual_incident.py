"""File an incident manually — no rule fired, an operator reports it directly.
alert_rule_id is always None for this path; source=MANUAL distinguishes it
from the two webhook-driven creation paths.

environment_id is body-only (mirrors CreateCloudflareConfig's precedent for
cloudflare_account_id) — no Depends() factory can resolve a body field as a
path-dependency parameter. Unlike that precedent, incident.create is itself
project-role-assignable, so the router cannot gate on ANY permission before
the body is parsed either (a global-only Layer-1 check would 403 a
project-role holder before their grant is ever consulted). This use case
resolves both project membership and the incident.create atom itself, via
ProjectsApi.resolve_effective_permissions — the same call
require_project_permission_for_environment makes, just invoked directly
instead of through a Depends factory."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.observability.constants import (
    AlertingAuditActions,
    AlertSeverity,
    IncidentCategory,
    IncidentSource,
)
from app.modules.observability.exceptions import (
    ObservabilityEnvironmentNotFound,
    ObservabilityPermissionDenied,
)
from app.modules.observability.schemas import IncidentRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.rbac.public import RbacActions, RbacApi, RbacResources
from app.modules.users.public import UserRead


class CreateManualIncident(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractObservabilityUnitOfWork,
        *,
        projects_api: ProjectsApi,
        rbac_api: RbacApi,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._projects_api = projects_api
        self._rbac_api = rbac_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        *,
        environment_id: UUID,
        category: IncidentCategory,
        severity: AlertSeverity,
        title: str,
        actor: UserRead,
    ) -> IncidentRead:
        environment = await self._projects_api.get_environment_by_id(environment_id)
        if environment is None:
            raise ObservabilityEnvironmentNotFound()

        permissions = await self._projects_api.resolve_effective_permissions(
            environment.project_id, actor, self._rbac_api
        )
        if f"{RbacResources.INCIDENT}.{RbacActions.CREATE}" not in permissions:
            raise ObservabilityPermissionDenied()

        incident = await self._uow.incidents.create(
            project_id=environment.project_id,
            environment_id=environment_id,
            alert_rule_id=None,
            source=IncidentSource.MANUAL,
            category=category,
            severity=severity,
            title=title,
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=AlertingAuditActions.INCIDENT_CREATED_MANUALLY,
            severity=AuditSeverity.INFO,
            message=f"Incident '{title}' filed manually",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            project_id=incident.project_id,
            environment_id=incident.environment_id,
            incident_id=str(incident.id),
        )
        return incident
