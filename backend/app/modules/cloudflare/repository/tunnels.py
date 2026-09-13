"""Single access path to the cloudflare_tunnels and tunnel_public_hostnames tables."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists as sa_exists
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.cloudflare.constants import (
    TunnelStatus,
)
from app.modules.cloudflare.exceptions import (
    CloudflareTunnelNotFound,
)
from app.modules.cloudflare.models import (
    CloudflareTunnel,
    TunnelPublicHostname,
)
from app.modules.cloudflare.schemas import (
    CloudflareTunnelRead,
)


class AbstractCloudflareTunnelRepository(AbstractRepository[CloudflareTunnelRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_account(self, cloudflare_account_id: UUID) -> list[CloudflareTunnelRead]:
        """Return every tunnel belonging to a Cloudflare account — used by
        SyncTunnels, which is account-wide, not environment-scoped."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_environment_via_hostnames(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        """Return every tunnel with at least one hostname matched to this
        environment — used by the environment's Tunnels page. A tunnel with
        no hostname matched to this environment never appears here, even if
        it belongs to the same Cloudflare account (it may be serving a
        sibling environment/project entirely)."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, cloudflare_account_id: UUID, cf_tunnel_id: str, name: str
    ) -> CloudflareTunnelRead:
        """Create a new tunnel row, status defaults to UNKNOWN."""
        raise NotImplementedError

    @abstractmethod
    async def update_status(
        self, tunnel_id: UUID, *, status: TunnelStatus, last_synced_at: datetime
    ) -> CloudflareTunnelRead:
        """Persist a fresh status reading from refresh-status."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_cf_tunnel_id(self, cf_tunnel_id: str) -> CloudflareTunnelRead | None:
        """Lookup by Cloudflare's tunnel UUID (not our internal UUID)."""
        raise NotImplementedError

    @abstractmethod
    async def upsert_from_sync(
        self,
        *,
        cloudflare_account_id: UUID,
        cf_tunnel_id: str,
        name: str,
        status: TunnelStatus,
        last_synced_at: datetime,
    ) -> CloudflareTunnelRead:
        """Insert or update a tunnel row from a Cloudflare API sync."""
        raise NotImplementedError

    @abstractmethod
    async def mark_missing_tunnels_down(
        self, *, cloudflare_account_id: UUID, active_cf_tunnel_ids: set[str], synced_at: datetime
    ) -> None:
        """Mark tunnels belonging to this account whose cf_tunnel_id is NOT in
        active_cf_tunnel_ids as DOWN."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, tunnel_id: UUID) -> None:
        """Delete a tunnel. tunnel_public_hostnames rows cascade at the DB level."""
        raise NotImplementedError


class CloudflareTunnelRepository(AbstractCloudflareTunnelRepository):
    """SQLAlchemy implementation. No cache-aside — Decision #8's reasoning
    (low-traffic, frequently-mutated) applies here identically."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> CloudflareTunnelRead | None:
        row = await self._session.get(CloudflareTunnel, entity_id)
        return CloudflareTunnelRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareTunnelRead], int]:
        """Required by AbstractRepository; tunnels are listed per-account in practice."""
        rows = await self._session.scalars(
            select(CloudflareTunnel).order_by(CloudflareTunnel.id).limit(limit).offset(offset)
        )
        items = [CloudflareTunnelRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(CloudflareTunnel))
        return items, total or 0

    @database
    async def list_for_account(self, cloudflare_account_id: UUID) -> list[CloudflareTunnelRead]:
        rows = await self._session.scalars(
            select(CloudflareTunnel)
            .where(CloudflareTunnel.cloudflare_account_id == cloudflare_account_id)
            .order_by(CloudflareTunnel.created_at)
        )
        return [CloudflareTunnelRead.model_validate(row) for row in rows]

    @database
    async def list_for_environment_via_hostnames(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        rows = await self._session.scalars(
            select(CloudflareTunnel)
            .where(
                sa_exists().where(
                    TunnelPublicHostname.tunnel_id == CloudflareTunnel.id,
                    TunnelPublicHostname.environment_id == environment_id,
                )
            )
            .order_by(CloudflareTunnel.created_at)
        )
        return [CloudflareTunnelRead.model_validate(row) for row in rows]

    @database
    async def create(
        self, *, cloudflare_account_id: UUID, cf_tunnel_id: str, name: str
    ) -> CloudflareTunnelRead:
        row = CloudflareTunnel(
            cloudflare_account_id=cloudflare_account_id, cf_tunnel_id=cf_tunnel_id, name=name
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareTunnelRead.model_validate(row)

    @database
    async def update_status(
        self, tunnel_id: UUID, *, status: TunnelStatus, last_synced_at: datetime
    ) -> CloudflareTunnelRead:
        row = await self._session.get(CloudflareTunnel, tunnel_id)
        if row is None:
            raise CloudflareTunnelNotFound()
        row.status = status
        row.last_synced_at = last_synced_at
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareTunnelRead.model_validate(row)

    @database
    async def get_by_cf_tunnel_id(self, cf_tunnel_id: str) -> CloudflareTunnelRead | None:
        row = await self._session.scalar(
            select(CloudflareTunnel).where(CloudflareTunnel.cf_tunnel_id == cf_tunnel_id)
        )
        return CloudflareTunnelRead.model_validate(row) if row else None

    @database
    async def upsert_from_sync(
        self,
        *,
        cloudflare_account_id: UUID,
        cf_tunnel_id: str,
        name: str,
        status: TunnelStatus,
        last_synced_at: datetime,
    ) -> CloudflareTunnelRead:
        row = await self._session.scalar(
            select(CloudflareTunnel).where(CloudflareTunnel.cf_tunnel_id == cf_tunnel_id)
        )
        if row is None:
            row = CloudflareTunnel(
                cloudflare_account_id=cloudflare_account_id,
                cf_tunnel_id=cf_tunnel_id,
                name=name,
                status=status,
                last_synced_at=last_synced_at,
            )
            self._session.add(row)
        else:
            row.cloudflare_account_id = cloudflare_account_id
            row.name = name
            row.status = status
            row.last_synced_at = last_synced_at
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareTunnelRead.model_validate(row)

    @database
    async def mark_missing_tunnels_down(
        self, *, cloudflare_account_id: UUID, active_cf_tunnel_ids: set[str], synced_at: datetime
    ) -> None:
        stmt = (
            sa_update(CloudflareTunnel)
            .where(CloudflareTunnel.cloudflare_account_id == cloudflare_account_id)
            .where(CloudflareTunnel.cf_tunnel_id.notin_(active_cf_tunnel_ids))
            .values(status=TunnelStatus.DOWN, last_synced_at=synced_at)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    @database
    async def delete(self, tunnel_id: UUID) -> None:
        row = await self._session.get(CloudflareTunnel, tunnel_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
