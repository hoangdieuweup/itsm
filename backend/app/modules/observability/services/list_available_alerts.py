"""List the Cloudflare alert types available to create a CLOUDFLARE_NATIVE
alert rule against — the picker's data source. Resolves the Cloudflare
account directly (this route is account-scoped, no environment involved)."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.public import CloudflareApi
from app.modules.observability.exceptions import CloudflareAccountNotFoundForAlerting
from app.modules.observability.schemas import AvailableAlertOption


class ListAvailableAlerts(AbstractUseCase):
    def __init__(self, cloudflare_api: CloudflareApi) -> None:
        self._cloudflare_api = cloudflare_api

    @use_case
    async def execute(self, account_id: UUID) -> list[AvailableAlertOption]:
        ready = await self._cloudflare_api.get_ready_client_for_account(account_id)
        if ready is None:
            raise CloudflareAccountNotFoundForAlerting()
        raw = await ready.client.list_available_alerts(
            cf_account_id=ready.cf_account_id, api_token=ready.api_token
        )
        return [
            AvailableAlertOption(
                alert_type=item["type"],
                display_name=(
                    item.get("display_name") or item.get("name") or item["type"].replace("_", " ").title()
                ),
            )
            for item in raw
        ]
