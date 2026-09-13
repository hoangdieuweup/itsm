"""Single access path to the cloudflare_configs table."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound
from app.modules.cloudflare.models import CloudflareConfig
from app.modules.cloudflare.schemas import CloudflareConfigRead


class AbstractCloudflareConfigRepository(AbstractRepository[CloudflareConfigRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def get_by_environment_id(self, environment_id: UUID) -> CloudflareConfigRead | None:
        """Look up the binding for one environment, or None if unbound."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, environment_id: UUID, cloudflare_account_id: UUID, zone_id: str, zone_name: str
    ) -> CloudflareConfigRead:
        """Create a new binding. Caller must confirm no existing binding for this environment first."""
        raise NotImplementedError

    @abstractmethod
    async def update_by_environment_id(
        self, environment_id: UUID, *, cloudflare_account_id: UUID, zone_id: str, zone_name: str
    ) -> CloudflareConfigRead:
        """Rebind an environment to a (possibly different) account + zone."""
        raise NotImplementedError

    @abstractmethod
    async def delete_by_environment_id(self, environment_id: UUID) -> None:
        """Remove an environment's binding."""
        raise NotImplementedError

    @abstractmethod
    async def list_environment_ids_for_account(self, cloudflare_account_id: UUID) -> list[UUID]:
        """Return every environment_id currently bound to this Cloudflare
        account — used by SyncTunnels to match hostnames against every
        sibling environment sharing the account, not just the one that
        triggered the sync."""
        raise NotImplementedError

    @abstractmethod
    async def list_environment_ids_for_zone(self, zone_id: str) -> list[UUID]:
        """Return every environment_id currently bound to this Cloudflare
        zone — used by SyncDnsRecords to match each record's name against
        every sibling environment sharing the zone, not just the one that
        triggered the sync. DNS records are zone-scoped, not account-scoped
        like Tunnels, so this filters on zone_id rather than
        cloudflare_account_id."""
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[CloudflareConfigRead]:
        """Return every cloudflare_configs row, unfiltered — the full set
        of Cloudflare-bound environments the drift reconciliation job must
        consider on each pass."""
        raise NotImplementedError


class CloudflareConfigRepository(AbstractCloudflareConfigRepository):
    """SQLAlchemy implementation. No cache-aside — Decision #8: low-traffic,
    high-mutation table, premature caching adds complexity with no measured
    benefit."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> CloudflareConfigRead | None:
        row = await self._session.get(CloudflareConfig, entity_id)
        return CloudflareConfigRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareConfigRead], int]:
        """Required by AbstractRepository; bindings are looked up per-environment in practice."""
        rows = await self._session.scalars(
            select(CloudflareConfig).order_by(CloudflareConfig.id).limit(limit).offset(offset)
        )
        items = [CloudflareConfigRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(CloudflareConfig))
        return items, total or 0

    @database
    async def get_by_environment_id(self, environment_id: UUID) -> CloudflareConfigRead | None:
        row = await self._session.scalar(
            select(CloudflareConfig).where(CloudflareConfig.environment_id == environment_id)
        )
        return CloudflareConfigRead.model_validate(row) if row else None

    @database
    async def create(
        self, *, environment_id: UUID, cloudflare_account_id: UUID, zone_id: str, zone_name: str
    ) -> CloudflareConfigRead:
        row = CloudflareConfig(
            environment_id=environment_id,
            cloudflare_account_id=cloudflare_account_id,
            zone_id=zone_id,
            zone_name=zone_name,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareConfigRead.model_validate(row)

    @database
    async def update_by_environment_id(
        self, environment_id: UUID, *, cloudflare_account_id: UUID, zone_id: str, zone_name: str
    ) -> CloudflareConfigRead:
        row = await self._session.scalar(
            select(CloudflareConfig).where(CloudflareConfig.environment_id == environment_id)
        )
        if row is None:
            raise CloudflareConfigNotFound()
        row.cloudflare_account_id = cloudflare_account_id
        row.zone_id = zone_id
        row.zone_name = zone_name
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareConfigRead.model_validate(row)

    @database
    async def delete_by_environment_id(self, environment_id: UUID) -> None:
        row = await self._session.scalar(
            select(CloudflareConfig).where(CloudflareConfig.environment_id == environment_id)
        )
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def list_environment_ids_for_account(self, cloudflare_account_id: UUID) -> list[UUID]:
        rows = await self._session.scalars(
            select(CloudflareConfig.environment_id).where(
                CloudflareConfig.cloudflare_account_id == cloudflare_account_id
            )
        )
        return list(rows)

    @database
    async def list_environment_ids_for_zone(self, zone_id: str) -> list[UUID]:
        rows = await self._session.scalars(
            select(CloudflareConfig.environment_id).where(CloudflareConfig.zone_id == zone_id)
        )
        return list(rows)

    @database
    async def list_all(self) -> list[CloudflareConfigRead]:
        rows = await self._session.scalars(select(CloudflareConfig).order_by(CloudflareConfig.created_at))
        return [CloudflareConfigRead.model_validate(row) for row in rows]
