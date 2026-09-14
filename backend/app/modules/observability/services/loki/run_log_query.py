"""Run a LogQL query against an environment's configured Loki instance."""

from datetime import datetime
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.loki.client import LokiClient
from app.integrations.loki.schemas import LokiQueryResult
from app.modules.observability.constants import ObservabilityLimits
from app.modules.observability.exceptions import LokiConfigNotFound
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.observability.utils import LokiAuthHelper


class RunLogQuery(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork, client: LokiClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(
        self, *, environment_id: UUID, query: str, start: datetime, end: datetime, limit: int
    ) -> LokiQueryResult:
        config = await self._uow.loki_configs.get_by_environment_id(environment_id)
        if config is None:
            raise LokiConfigNotFound()

        credential = await self._uow.loki_configs.get_credential(environment_id)
        auth_header = LokiAuthHelper.resolve_loki_auth_header(config, credential)

        clamped_limit = min(limit, ObservabilityLimits.MAX_QUERY_LIMIT)
        return await self._client.query_range(
            endpoint_url=config.endpoint_url,
            query=query,
            start=start,
            end=end,
            tenant_id=config.tenant_id,
            auth_header=auth_header,
            limit=clamped_limit,
        )
