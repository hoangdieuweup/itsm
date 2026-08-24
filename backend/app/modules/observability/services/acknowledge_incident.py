"""Acknowledge an incident. OPEN -> ACKNOWLEDGED only (IncidentRules.validate_transition
rejects anything else, including RESOLVED -> ACKNOWLEDGED)."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.observability.constants import AlertingAuditActions, IncidentStatus
from app.modules.observability.exceptions import IncidentNotFound
from app.modules.observability.rules import IncidentRules
from app.modules.observability.schemas import IncidentRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.users.public import UserRead


class AcknowledgeIncident(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork, *, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, incident_id: UUID, *, actor: UserRead) -> IncidentRead:
        incident = await self._uow.incidents.get_by_id(incident_id)
        if incident is None:
            raise IncidentNotFound()
        IncidentRules.validate_transition(incident.status, IncidentStatus.ACKNOWLEDGED)
        result = await self._uow.incidents.update_status(
            incident_id, status=IncidentStatus.ACKNOWLEDGED, actor_id=actor.id, at=datetime.now(UTC)
        )
        await self._uow.commit()
        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=AlertingAuditActions.INCIDENT_ACKNOWLEDGED,
            severity=AuditSeverity.INFO,
            message=f"Incident '{incident.title}' acknowledged",
            actor=AuditActor(user_id=actor.id, email=actor.email),
            project_id=incident.project_id,
            environment_id=incident.environment_id,
            incident_id=str(incident_id),
        )
        return result
