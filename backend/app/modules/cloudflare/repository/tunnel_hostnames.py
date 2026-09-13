"""Single access path to the tunnel_public_hostnames table."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.cloudflare.constants import ManagedBy
from app.modules.cloudflare.exceptions import TunnelPublicHostnameNotFound
from app.modules.cloudflare.models import TunnelPublicHostname
from app.modules.cloudflare.schemas import TunnelPublicHostnameRead


class AbstractTunnelHostnameRepository(AbstractRepository[TunnelPublicHostnameRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_tunnel(
        self, tunnel_id: UUID, *, environment_id: UUID | None = None
    ) -> list[TunnelPublicHostnameRead]:
        """Return every hostname published through a tunnel. When
        environment_id is given, narrow to only the hostnames matched to
        that environment — used by the per-environment hostnames panel so a
        tunnel shared with another project never leaks that project's
        internal service URL onto this page."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        tunnel_id: UUID,
        hostname: str,
        service: str,
        created_by: UUID | None,
        environment_id: UUID | None = None,
    ) -> TunnelPublicHostnameRead:
        """Create a new hostname row. Caller must have already confirmed the
        Cloudflare ingress PUT succeeded. environment_id, when given, is the
        environment the caller was managing this tunnel from — set eagerly
        so a freshly-created hostname shows up immediately on that
        environment's Tunnels page instead of waiting for the next sync."""
        raise NotImplementedError

    @abstractmethod
    async def update_service(self, hostname_id: UUID, *, service: str) -> TunnelPublicHostnameRead:
        """Update a hostname's service target. hostname itself is immutable."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, hostname_id: UUID) -> None:
        """Delete a hostname row."""
        raise NotImplementedError

    @abstractmethod
    async def upsert_from_sync(
        self,
        *,
        tunnel_id: UUID,
        hostname: str,
        service: str,
        environment_id: UUID | None,
        last_synced_at: datetime,
    ) -> TunnelPublicHostnameRead:
        """Insert or update a hostname row from a Cloudflare API sync,
        matching it to environment_id (may be None — no bound environment's
        base_url matched this hostname)."""
        raise NotImplementedError

    @abstractmethod
    async def delete_not_in_hostnames(self, tunnel_id: UUID, keep_hostnames: set[str]) -> None:
        """Delete local hostname rows for this tunnel whose hostname is NOT
        in the given set (they were removed on Cloudflare)."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_environment(self, environment_id: UUID) -> list[TunnelPublicHostnameRead]:
        """Return every hostname matched to environment_id, across ALL
        tunnels on the account — distinct from list_for_tunnel, which needs
        an already-known tunnel_id. Backs the drift reconciliation job's
        account-wide before/after snapshot (a single environment's matched
        hostnames can live on more than one tunnel sharing the account)."""
        raise NotImplementedError


class TunnelHostnameRepository(AbstractTunnelHostnameRepository):
    """SQLAlchemy implementation. No cache-aside — Decision #8."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> TunnelPublicHostnameRead | None:
        row = await self._session.get(TunnelPublicHostname, entity_id)
        return TunnelPublicHostnameRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[TunnelPublicHostnameRead], int]:
        """Required by AbstractRepository; hostnames are listed per-tunnel in practice."""
        rows = await self._session.scalars(
            select(TunnelPublicHostname).order_by(TunnelPublicHostname.id).limit(limit).offset(offset)
        )
        items = [TunnelPublicHostnameRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(TunnelPublicHostname))
        return items, total or 0

    @database
    async def list_for_tunnel(
        self, tunnel_id: UUID, *, environment_id: UUID | None = None
    ) -> list[TunnelPublicHostnameRead]:
        stmt = select(TunnelPublicHostname).where(TunnelPublicHostname.tunnel_id == tunnel_id)
        if environment_id is not None:
            stmt = stmt.where(TunnelPublicHostname.environment_id == environment_id)
        rows = await self._session.scalars(stmt.order_by(TunnelPublicHostname.created_at))
        return [TunnelPublicHostnameRead.model_validate(row) for row in rows]

    @database
    async def create(
        self,
        *,
        tunnel_id: UUID,
        hostname: str,
        service: str,
        created_by: UUID | None,
        environment_id: UUID | None = None,
    ) -> TunnelPublicHostnameRead:
        row = TunnelPublicHostname(
            tunnel_id=tunnel_id,
            hostname=hostname,
            service=service,
            environment_id=environment_id,
            managed_by=ManagedBy.SYSTEM,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return TunnelPublicHostnameRead.model_validate(row)

    @database
    async def update_service(self, hostname_id: UUID, *, service: str) -> TunnelPublicHostnameRead:
        row = await self._session.get(TunnelPublicHostname, hostname_id)
        if row is None:
            raise TunnelPublicHostnameNotFound()
        row.service = service
        await self._session.flush()
        await self._session.refresh(row)
        return TunnelPublicHostnameRead.model_validate(row)

    @database
    async def delete(self, hostname_id: UUID) -> None:
        row = await self._session.get(TunnelPublicHostname, hostname_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def upsert_from_sync(
        self,
        *,
        tunnel_id: UUID,
        hostname: str,
        service: str,
        environment_id: UUID | None,
        last_synced_at: datetime,
    ) -> TunnelPublicHostnameRead:
        row = await self._session.scalar(
            select(TunnelPublicHostname).where(TunnelPublicHostname.hostname == hostname)
        )
        if row is None:
            row = TunnelPublicHostname(
                tunnel_id=tunnel_id,
                hostname=hostname,
                service=service,
                environment_id=environment_id,
                managed_by=ManagedBy.EXTERNAL,
                last_synced_at=last_synced_at,
            )
            self._session.add(row)
        else:
            row.tunnel_id = tunnel_id
            row.service = service
            row.environment_id = environment_id
            row.last_synced_at = last_synced_at
        await self._session.flush()
        await self._session.refresh(row)
        return TunnelPublicHostnameRead.model_validate(row)

    @database
    async def delete_not_in_hostnames(self, tunnel_id: UUID, keep_hostnames: set[str]) -> None:
        stmt = (
            sa_delete(TunnelPublicHostname)
            .where(TunnelPublicHostname.tunnel_id == tunnel_id)
            .where(TunnelPublicHostname.hostname.notin_(keep_hostnames))
        )
        await self._session.execute(stmt)
        await self._session.flush()

    @database
    async def list_for_environment(self, environment_id: UUID) -> list[TunnelPublicHostnameRead]:
        rows = await self._session.scalars(
            select(TunnelPublicHostname)
            .where(TunnelPublicHostname.environment_id == environment_id)
            .order_by(TunnelPublicHostname.created_at)
        )
        return [TunnelPublicHostnameRead.model_validate(row) for row in rows]
