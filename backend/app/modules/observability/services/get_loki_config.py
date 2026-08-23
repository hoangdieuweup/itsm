from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.observability.exceptions import LokiConfigNotFound
from app.modules.observability.schemas import LokiConfigRead
from app.modules.observability.uow import AbstractObservabilityUnitOfWork


class GetLokiConfig(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID) -> LokiConfigRead:
        config = await self._uow.loki_configs.get_by_environment_id(environment_id)
        if config is None:
            raise LokiConfigNotFound()
        return config
