"""Single access path to the dns_records table."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.cloudflare.constants import (
    DnsRecordType,
    ManagedBy,
)
from app.modules.cloudflare.exceptions import DnsRecordNotFound
from app.modules.cloudflare.models import DnsRecord
from app.modules.cloudflare.schemas import DnsRecordRead


class AbstractDnsRecordRepository(AbstractRepository[DnsRecordRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_environment(self, environment_id: UUID) -> list[DnsRecordRead]:
        """Return every DNS record belonging to an environment."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        environment_id: UUID,
        cf_record_id: str,
        record_type: DnsRecordType,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        created_by: UUID | None,
    ) -> DnsRecordRead:
        """Create a new DNS record row. Caller must have already confirmed the Cloudflare write succeeded."""
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, record_id: UUID, *, content: str, priority: int | None, proxied: bool, ttl: int
    ) -> DnsRecordRead:
        """Update a record's mutable fields. record_type/name are immutable after creation."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, record_id: UUID) -> None:
        """Delete a DNS record row."""
        raise NotImplementedError

    @abstractmethod
    async def upsert_from_sync(
        self,
        *,
        environment_id: UUID | None,
        cf_record_id: str,
        record_type: DnsRecordType,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        managed_by: ManagedBy,
        last_synced_at: datetime,
    ) -> DnsRecordRead:
        """Insert or update a DNS record row from a Cloudflare API sync.
        environment_id is the freshly-recomputed match for this pass (None
        if no bound environment's base_url matches this record's name) —
        applied on both insert AND update, so a record's attribution
        self-heals on every sync rather than being fixed at first
        discovery."""
        raise NotImplementedError

    @abstractmethod
    async def delete_not_in_cf_ids(self, environment_ids: list[UUID], keep_cf_ids: set[str]) -> None:
        """Delete local records attributed to any of the given environments
        whose cf_record_id is NOT in the given set (they were deleted on
        Cloudflare). Takes every sibling environment sharing the synced
        zone, not just the one that triggered the sync — otherwise a
        record belonging to a sibling would only ever get cleaned up when
        that specific sibling happens to sync. Records with
        environment_id=None (matching no known environment) are not swept
        by this — same accepted, disclosed gap as unmatched Tunnel
        hostnames."""
        raise NotImplementedError


class DnsRecordRepository(AbstractDnsRecordRepository):
    """SQLAlchemy implementation. No cache-aside — Decision #8."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> DnsRecordRead | None:
        row = await self._session.get(DnsRecord, entity_id)
        return DnsRecordRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[DnsRecordRead], int]:
        """Required by AbstractRepository; records are listed per-environment in practice."""
        rows = await self._session.scalars(
            select(DnsRecord).order_by(DnsRecord.id).limit(limit).offset(offset)
        )
        items = [DnsRecordRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(DnsRecord))
        return items, total or 0

    @database
    async def list_for_environment(self, environment_id: UUID) -> list[DnsRecordRead]:
        rows = await self._session.scalars(
            select(DnsRecord).where(DnsRecord.environment_id == environment_id).order_by(DnsRecord.created_at)
        )
        return [DnsRecordRead.model_validate(row) for row in rows]

    @database
    async def create(
        self,
        *,
        environment_id: UUID,
        cf_record_id: str,
        record_type: DnsRecordType,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        created_by: UUID | None,
    ) -> DnsRecordRead:
        row = DnsRecord(
            environment_id=environment_id,
            cf_record_id=cf_record_id,
            record_type=record_type,
            name=name,
            content=content,
            priority=priority,
            proxied=proxied,
            ttl=ttl,
            managed_by=ManagedBy.SYSTEM,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return DnsRecordRead.model_validate(row)

    @database
    async def update(
        self, record_id: UUID, *, content: str, priority: int | None, proxied: bool, ttl: int
    ) -> DnsRecordRead:
        row = await self._session.get(DnsRecord, record_id)
        if row is None:
            raise DnsRecordNotFound()
        row.content = content
        row.priority = priority
        row.proxied = proxied
        row.ttl = ttl
        await self._session.flush()
        await self._session.refresh(row)
        return DnsRecordRead.model_validate(row)

    @database
    async def delete(self, record_id: UUID) -> None:
        row = await self._session.get(DnsRecord, record_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def upsert_from_sync(
        self,
        *,
        environment_id: UUID | None,
        cf_record_id: str,
        record_type: DnsRecordType,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        managed_by: ManagedBy,
        last_synced_at: datetime,
    ) -> DnsRecordRead:
        row = await self._session.scalar(select(DnsRecord).where(DnsRecord.cf_record_id == cf_record_id))
        if row is None:
            row = DnsRecord(
                environment_id=environment_id,
                cf_record_id=cf_record_id,
                record_type=record_type,
                name=name,
                content=content,
                priority=priority,
                proxied=proxied,
                ttl=ttl,
                managed_by=managed_by,
                last_synced_at=last_synced_at,
            )
            self._session.add(row)
        else:
            if row.managed_by == ManagedBy.EXTERNAL:
                row.environment_id = environment_id
            row.record_type = record_type
            row.name = name
            row.content = content
            row.priority = priority
            row.proxied = proxied
            row.ttl = ttl
            row.last_synced_at = last_synced_at
        await self._session.flush()
        await self._session.refresh(row)
        return DnsRecordRead.model_validate(row)

    @database
    async def delete_not_in_cf_ids(self, environment_ids: list[UUID], keep_cf_ids: set[str]) -> None:
        stmt = (
            sa_delete(DnsRecord)
            .where(DnsRecord.environment_id.in_(environment_ids))
            .where(DnsRecord.cf_record_id.notin_(keep_cf_ids))
        )
        await self._session.execute(stmt)
        await self._session.flush()
