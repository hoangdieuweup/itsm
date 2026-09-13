"""Single access path to the cloudflare_accounts table."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.constants import (
    CloudflareAccountsCacheKeys,
)
from app.modules.cloudflare.exceptions import (
    CloudflareAccountNotFound,
)
from app.modules.cloudflare.models import (
    CloudflareAccount,
)
from app.modules.cloudflare.schemas import (
    CloudflareAccountRead,
)


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
    async def list_all(self) -> list[CloudflareAccountRead]:
        """Return every account ordered by label — backs the manage_all view
        of GET /cloudflare-accounts, which is not paginated."""
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
    async def list_all(self) -> list[CloudflareAccountRead]:
        """Return every account ordered by label."""
        rows = await self._session.scalars(select(CloudflareAccount).order_by(CloudflareAccount.label))
        return [CloudflareAccountRead.model_validate(row) for row in rows]

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
            raise CloudflareAccountNotFound()
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
            raise CloudflareAccountNotFound()
        row.cf_webhook_destination_id = cf_webhook_destination_id
        row.webhook_secret_ciphertext = secret_ciphertext
        await self._session.flush()
