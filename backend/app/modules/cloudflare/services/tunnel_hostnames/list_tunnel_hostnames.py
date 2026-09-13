"""List every public hostname published through one tunnel."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, CloudflareTunnelNotFound
from app.modules.cloudflare.rules import TunnelOwnershipRules
from app.modules.cloudflare.schemas import TunnelPublicHostnameRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListTunnelHostnames(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID, tunnel_id: UUID) -> list[TunnelPublicHostnameRead]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if not TunnelOwnershipRules.verify_tunnel_belongs_to_account(tunnel, config.cloudflare_account_id):
            raise CloudflareTunnelNotFound()
        return await self._uow.tunnel_hostnames.list_for_tunnel(tunnel_id, environment_id=environment_id)
