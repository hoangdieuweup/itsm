"""Single access path to the cloudflare_account_managers table."""

from abc import abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.core.models import FrozenModel
from app.core.pagination import PageQuery
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.models import CloudflareAccountManager


class CloudflareAccountManagerRow(FrozenModel):
    """Raw manager row — no email/name (the repository has no cross-module
    knowledge of users; enrichment happens in the service layer via UsersApi)."""

    cloudflare_account_id: UUID
    user_id: UUID
    access_level: AccessLevel
    created_at: datetime


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
        rows, total = await PageQuery.fetch_rows(
            self._session,
            CloudflareAccountManager,
            limit=limit,
            offset=offset,
        )
        return [CloudflareAccountManagerRow.model_validate(row) for row in rows], total

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
