"""Fetch a single incident by id."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.observability.exceptions import IncidentNotFound
from app.modules.observability.schemas import IncidentRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork


class GetIncident(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, incident_id: UUID) -> IncidentRead:
        incident = await self._uow.incidents.get_by_id(incident_id)
        if incident is None:
            raise IncidentNotFound()
        return incident
