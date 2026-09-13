"""List incidents, optionally filtered by project/environment/status."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.observability.constants import IncidentStatus
from app.modules.observability.schemas import IncidentRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork


class ListIncidents(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(
        self,
        *,
        project_id: UUID | None = None,
        environment_id: UUID | None = None,
        status: IncidentStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[IncidentRead], int]:
        return await self._uow.incidents.list_page_filtered(
            project_id=project_id, environment_id=environment_id, status=status, limit=limit, offset=offset
        )
