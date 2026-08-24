"""File an incident manually — no rule fired, an operator reports it directly.
alert_rule_id is always None for this path; source=MANUAL distinguishes it
from the two webhook-driven creation paths."""

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
from app.modules.observability.exceptions import ObservabilityEnvironmentNotFound
from app.modules.observability.schemas import IncidentRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead


class CreateManualIncident(AbstractUseCase):
    def __init__(
        self, uow: AbstractObservabilityUnitOfWork, *, projects_api: ProjectsApi, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._projects_api = projects_api
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
