"""List DNS records for a bound environment."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound
from app.modules.cloudflare.schemas import DnsRecordRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListDnsRecords(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID) -> list[DnsRecordRead]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        return await self._uow.dns_records.list_for_environment(environment_id)
