"""Get an environment's aggregated Cloudflare traffic stats (GraphQL
Analytics — Free-plan compatible), filtered to the environment's own
hostname. Same resolve-config -> resolve-account -> decrypt-token ->
call-client shape as every other Cloudflare read use case in this module."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.schemas import CloudflareTrafficStats
from app.modules.cloudflare.exceptions import (
    CloudflareAccountNotFound,
    CloudflareConfigNotFound,
    EnvironmentBaseUrlNotConfigured,
)
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.projects.public import ProjectsApi

DEFAULT_RANGE = timedelta(hours=24)


class GetCloudflareTrafficStats(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, projects_api: ProjectsApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._projects_api = projects_api

    @use_case
    async def execute(
        self, *, environment_id: UUID, since: datetime | None, until: datetime | None
    ) -> CloudflareTrafficStats:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()

        environment = await self._projects_api.get_environment_by_id(environment_id)
        hostname = urlparse(environment.base_url).hostname if environment and environment.base_url else None
        if hostname is None:
            raise EnvironmentBaseUrlNotConfigured()

        credentials = await self._uow.accounts.get_credentials(config.cloudflare_account_id)
        if credentials is None:
            raise CloudflareAccountNotFound()

        resolved_until = until or datetime.now(UTC)
        resolved_since = since or (resolved_until - DEFAULT_RANGE)

        return await self._client.get_zone_traffic_stats(
            zone_id=config.zone_id,
            api_token=credentials.api_token,
            hostname=hostname,
            since=resolved_since,
            until=resolved_until,
        )
