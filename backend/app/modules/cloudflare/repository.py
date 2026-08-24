"""Single access path to the cloudflare_accounts and cloudflare_account_managers tables."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import exists as sa_exists
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.core.models import FrozenModel
from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.constants import (
    AccessLevel,
    CloudflareAccountsCacheKeys,
    DnsRecordType,
    ManagedBy,
    TunnelStatus,
)
from app.modules.cloudflare.models import (
    CloudflareAccount,
    CloudflareAccountManager,
    CloudflareConfig,
    CloudflareTunnel,
    DnsRecord,
    TunnelPublicHostname,
)
from app.modules.cloudflare.schemas import (
    CloudflareAccountRead,
    CloudflareConfigRead,
    CloudflareTunnelRead,
    DnsRecordRead,
    TunnelPublicHostnameRead,
)


class CloudflareAccountManagerRow(FrozenModel):
    """Raw manager row — no email/name (the repository has no cross-module
    knowledge of users; enrichment happens in the service layer via UsersApi)."""

    cloudflare_account_id: UUID
    user_id: UUID
    access_level: AccessLevel
    created_at: datetime


class AbstractCloudflareAccountRepository(AbstractRepository[CloudflareAccountRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def create(
        self, *, label: str, cf_account_id: str, api_token: str, created_by: UUID | None
    ) -> CloudflareAccountRead:
        """Create a new account. api_token must already be Fernet-ciphertext."""
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, account_id: UUID, *, label: str | None, api_token: str | None
    ) -> CloudflareAccountRead:
        """Rename and/or rotate the token. api_token, if given, must already be ciphertext."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, account_id: UUID) -> None:
        """Delete an account. Its manager rows cascade at the DB level."""
        raise NotImplementedError

    @abstractmethod
    async def get_token_ciphertext(self, account_id: UUID) -> str | None:
        """Return the raw (still-encrypted) api_token column, or None if the
        account doesn't exist. Bypasses the cache-aside CloudflareAccountRead
        entirely — a secret never enters the cache."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_ids(self, account_ids: list[UUID]) -> list[CloudflareAccountRead]:
        """Return every account whose id is in account_ids, in no particular
        order — backs the filtered GET /cloudflare-accounts list."""
        raise NotImplementedError

    @abstractmethod
    async def get_webhook_destination_ciphertext(self, account_id: UUID) -> tuple[str | None, str | None]:
        """Return (cf_webhook_destination_id, webhook_secret_ciphertext), both
        None if a webhook destination was never registered for this account."""
        raise NotImplementedError

    @abstractmethod
    async def set_webhook_destination(
        self, account_id: UUID, *, cf_webhook_destination_id: str, secret_ciphertext: str
    ) -> None:
        """Persist a newly-registered webhook destination."""
        raise NotImplementedError


class CloudflareAccountRepository(AbstractCloudflareAccountRepository):
    """SQLAlchemy implementation. Every read/write of cloudflare_accounts goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: UUID) -> CloudflareAccountRead | None:
        """Return one account, or None when it does not exist. Cache-aside."""
        return await self._cache.get_or_load(
            CloudflareAccountsCacheKeys.ACCOUNT_ENTITY,
            entity_id,
            CloudflareAccountRead,
            lambda: self._load_by_id(entity_id),
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> CloudflareAccountRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(CloudflareAccount).where(CloudflareAccount.id == entity_id))
        return CloudflareAccountRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountRead], int]:
        """Required by AbstractRepository; the router never lists unfiltered —
        see list_for_ids, which backs the actual GET /cloudflare-accounts route."""
        rows = await self._session.scalars(
            select(CloudflareAccount).order_by(CloudflareAccount.id).limit(limit).offset(offset)
        )
        items = [CloudflareAccountRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(CloudflareAccount))
        return items, total or 0

    @database
    async def list_for_ids(self, account_ids: list[UUID]) -> list[CloudflareAccountRead]:
        """Return every account whose id is in account_ids."""
        if not account_ids:
            return []
        rows = await self._session.scalars(
            select(CloudflareAccount).where(CloudflareAccount.id.in_(account_ids))
        )
        return [CloudflareAccountRead.model_validate(row) for row in rows]

    @database
    async def create(
        self, *, label: str, cf_account_id: str, api_token: str, created_by: UUID | None
    ) -> CloudflareAccountRead:
        """Create a new account."""
        row = CloudflareAccount(
            label=label, cf_account_id=cf_account_id, api_token=api_token, created_by=created_by
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareAccountRead.model_validate(row)

    @database
    async def update(
        self, account_id: UUID, *, label: str | None, api_token: str | None
    ) -> CloudflareAccountRead:
        """Rename and/or rotate the token. Caller must confirm account_id exists first."""
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None:
            raise ValueError(f"cloudflare account {account_id} does not exist")
        if label is not None:
            row.label = label
        if api_token is not None:
            row.api_token = api_token
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareAccountRead.model_validate(row)

    @database
    async def delete(self, account_id: UUID) -> None:
        """Delete an account. Caller must confirm account_id exists first."""
        row = await self._session.get(CloudflareAccount, account_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def get_token_ciphertext(self, account_id: UUID) -> str | None:
        """Return the raw api_token column, still Fernet-ciphertext. Never cached."""
        row = await self._session.get(CloudflareAccount, account_id)
        return row.api_token if row is not None else None

    @database
    async def get_webhook_destination_ciphertext(self, account_id: UUID) -> tuple[str | None, str | None]:
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None:
            return None, None
        return row.cf_webhook_destination_id, row.webhook_secret_ciphertext

    @database
    async def set_webhook_destination(
        self, account_id: UUID, *, cf_webhook_destination_id: str, secret_ciphertext: str
    ) -> None:
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None:
            raise ValueError(f"cloudflare account {account_id} does not exist")
        row.cf_webhook_destination_id = cf_webhook_destination_id
        row.webhook_secret_ciphertext = secret_ciphertext
        await self._session.flush()


class AbstractCloudflareAccountManagerRepository(AbstractRepository[CloudflareAccountManagerRow, tuple]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def get_for_user(self, account_id: UUID, user_id: UUID) -> CloudflareAccountManagerRow | None:
        """Look up one user's manager row on one account, or None if they have no access."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_account(self, account_id: UUID) -> list[CloudflareAccountManagerRow]:
        """Return every manager row for one account."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_user(self, user_id: UUID) -> list[CloudflareAccountManagerRow]:
        """Return every manager row for one user — backs the filtered account list."""
        raise NotImplementedError

    @abstractmethod
    async def count_owners(self, account_id: UUID) -> int:
        """Count OWNER-level rows on one account."""
        raise NotImplementedError

    @abstractmethod
    async def upsert(
        self, account_id: UUID, user_id: UUID, access_level: AccessLevel
    ) -> CloudflareAccountManagerRow:
        """Insert or update a manager row."""
        raise NotImplementedError

    @abstractmethod
    async def remove(self, account_id: UUID, user_id: UUID) -> None:
        """Delete a manager row. No-op if it doesn't exist."""
        raise NotImplementedError


class CloudflareAccountManagerRepository(AbstractCloudflareAccountManagerRepository):
    """SQLAlchemy implementation. Every read/write of cloudflare_account_managers goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: tuple) -> CloudflareAccountManagerRow | None:
        """Required by AbstractRepository; callers use get_for_user instead."""
        account_id, user_id = entity_id
        return await self.get_for_user(account_id, user_id)

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountManagerRow], int]:
        """Required by AbstractRepository; manager rows are listed per-account in practice."""
        rows = await self._session.scalars(select(CloudflareAccountManager).limit(limit).offset(offset))
        items = [CloudflareAccountManagerRow.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(CloudflareAccountManager))
        return items, total or 0

    @database
    async def get_for_user(self, account_id: UUID, user_id: UUID) -> CloudflareAccountManagerRow | None:
        """Look up one user's manager row on one account."""
        row = await self._session.get(CloudflareAccountManager, (account_id, user_id))
        return CloudflareAccountManagerRow.model_validate(row) if row else None

    @database
    async def list_for_account(self, account_id: UUID) -> list[CloudflareAccountManagerRow]:
        """Return every manager row for one account."""
        rows = await self._session.scalars(
            select(CloudflareAccountManager)
            .where(CloudflareAccountManager.cloudflare_account_id == account_id)
            .order_by(CloudflareAccountManager.created_at)
        )
        return [CloudflareAccountManagerRow.model_validate(row) for row in rows]

    @database
    async def list_for_user(self, user_id: UUID) -> list[CloudflareAccountManagerRow]:
        """Return every manager row for one user."""
        rows = await self._session.scalars(
            select(CloudflareAccountManager).where(CloudflareAccountManager.user_id == user_id)
        )
        return [CloudflareAccountManagerRow.model_validate(row) for row in rows]

    @database
    async def count_owners(self, account_id: UUID) -> int:
        """Count OWNER-level rows on one account."""
        count = await self._session.scalar(
            select(func.count())
            .select_from(CloudflareAccountManager)
            .where(
                CloudflareAccountManager.cloudflare_account_id == account_id,
                CloudflareAccountManager.access_level == AccessLevel.OWNER,
            )
        )
        return count or 0

    @database
    async def upsert(
        self, account_id: UUID, user_id: UUID, access_level: AccessLevel
    ) -> CloudflareAccountManagerRow:
        """Insert or update a manager row."""
        row = await self._session.get(CloudflareAccountManager, (account_id, user_id))
        if row is None:
            row = CloudflareAccountManager(
                cloudflare_account_id=account_id, user_id=user_id, access_level=access_level
            )
            self._session.add(row)
        else:
            row.access_level = access_level
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareAccountManagerRow.model_validate(row)

    @database
    async def remove(self, account_id: UUID, user_id: UUID) -> None:
        """Delete a manager row. No-op if it doesn't exist."""
        row = await self._session.get(CloudflareAccountManager, (account_id, user_id))
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


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
            raise ValueError(f"cloudflare config for environment {environment_id} does not exist")
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
    async def list_all(self) -> list[CloudflareConfigRead]:
        rows = await self._session.scalars(select(CloudflareConfig).order_by(CloudflareConfig.created_at))
        return [CloudflareConfigRead.model_validate(row) for row in rows]


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
        environment_id: UUID,
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
        """Insert or update a DNS record row from a Cloudflare API sync."""
        raise NotImplementedError

    @abstractmethod
    async def delete_not_in_cf_ids(self, environment_id: UUID, keep_cf_ids: set[str]) -> None:
        """Delete local records whose cf_record_id is NOT in the given set
        (they were deleted on Cloudflare)."""
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
            raise ValueError(f"dns record {record_id} does not exist")
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
        environment_id: UUID,
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
    async def delete_not_in_cf_ids(self, environment_id: UUID, keep_cf_ids: set[str]) -> None:
        stmt = (
            sa_delete(DnsRecord)
            .where(DnsRecord.environment_id == environment_id)
            .where(DnsRecord.cf_record_id.notin_(keep_cf_ids))
        )
        await self._session.execute(stmt)
        await self._session.flush()


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
            raise ValueError(f"cloudflare tunnel {tunnel_id} does not exist")
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
            raise ValueError(f"tunnel hostname {hostname_id} does not exist")
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
