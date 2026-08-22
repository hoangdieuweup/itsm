"""Single access path to the cloudflare_accounts and cloudflare_account_managers tables."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.core.models import FrozenModel
from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountsCacheKeys
from app.modules.cloudflare.models import CloudflareAccount, CloudflareAccountManager
from app.modules.cloudflare.schemas import CloudflareAccountRead


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
