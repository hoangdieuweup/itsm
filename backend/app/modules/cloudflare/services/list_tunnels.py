"""List every tunnel for an environment. One environment may have MANY
tunnels (1:N, unlike cloudflare_configs' 1:1 binding to an account/zone)."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.schemas import CloudflareTunnelRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListTunnels(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        return await self._uow.tunnels.list_for_environment(environment_id)
