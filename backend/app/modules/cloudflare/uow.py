"""Transaction boundary for the cloudflare module."""

import logging
from abc import abstractmethod
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    AbstractCloudflareConfigRepository,
    AbstractDnsRecordRepository,
    CloudflareAccountManagerRepository,
    CloudflareAccountRepository,
    CloudflareConfigRepository,
    DnsRecordRepository,
)

logger = logging.getLogger(__name__)


class AbstractCloudflareUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    accounts: AbstractCloudflareAccountRepository
    account_managers: AbstractCloudflareAccountManagerRepository
    configs: AbstractCloudflareConfigRepository
    dns_records: AbstractDnsRecordRepository

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        """Queue a cache entity for invalidation once THIS uow's own commit() runs."""
        raise NotImplementedError


class CloudflareUnitOfWork(AbstractCloudflareUnitOfWork):
    """Owns the transaction for the cloudflare module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, UUID]] = []
        self.accounts = CloudflareAccountRepository(session, cache)
        self.account_managers = CloudflareAccountManagerRepository(session)
        self.configs = CloudflareConfigRepository(session)
        self.dns_records = DnsRecordRepository(session)

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

    @database
    async def commit(self) -> None:
        """Commit the transaction, then invalidate every queued cache entity —
        strictly after the database commit, per references/caching.md#order-of-operations."""
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction and drop any queued invalidation."""
        await self._session.rollback()
        self._stale.clear()
        logger.warning("cloudflare unit of work rolled back")
