"""List every tunnel actually serving an environment. Tunnels are
account-scoped (many environments/projects may share one), so "serving this
environment" means at least one of the tunnel's public hostnames matched
this environment's base_url — see list_for_environment_via_hostnames and
TunnelHostnameRules.match_environment_id."""

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
        return await self._uow.tunnels.list_for_environment_via_hostnames(environment_id)
