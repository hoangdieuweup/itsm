"""List alert rules for an environment."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.observability.schemas import AlertRuleRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork


class ListAlertRules(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID) -> list[AlertRuleRead]:
        return await self._uow.alert_rules.list_for_environment(environment_id)
