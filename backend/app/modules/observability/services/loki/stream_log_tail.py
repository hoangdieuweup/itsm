"""Stream new log lines for an environment's configured Loki instance as
they arrive, for the SSE live-tail endpoint."""

from collections.abc import AsyncIterator
from uuid import UUID

from app.core.base.markers import sse_event
from app.core.base.use_case import AbstractUseCase
from app.integrations.loki.client import LokiClient
from app.integrations.loki.schemas import LokiLogEntry
from app.modules.observability.exceptions import LokiConfigNotFound
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.observability.utils import LokiAuthHelper


class StreamLogTail(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork, client: LokiClient) -> None:
        self._uow = uow
        self._client = client

    @sse_event
    async def execute(self, *, environment_id: UUID, query: str, limit: int) -> AsyncIterator[LokiLogEntry]:
        config = await self._uow.loki_configs.get_by_environment_id(environment_id)
        if config is None:
            raise LokiConfigNotFound()

        ciphertext = await self._uow.loki_configs.get_credential_ciphertext(environment_id)
        auth_header = LokiAuthHelper.resolve_loki_auth_header(config, ciphertext)

        async for entry in self._client.tail(
            endpoint_url=config.endpoint_url,
            query=query,
            tenant_id=config.tenant_id,
            auth_header=auth_header,
            limit=limit,
        ):
            yield entry
