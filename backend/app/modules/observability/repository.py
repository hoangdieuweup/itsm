"""Single access path to the loki_configs table."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.modules.observability.constants import LokiAuthType
from app.modules.observability.models import LokiConfig
from app.modules.observability.schemas import LokiConfigRead


class AbstractLokiConfigRepository(AbstractRepository[LokiConfigRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def get_by_environment_id(self, environment_id: UUID) -> LokiConfigRead | None:
        """Look up the Loki config for one environment, or None if unconfigured."""
        raise NotImplementedError

    @abstractmethod
    async def get_credential_ciphertext(self, environment_id: UUID) -> str | None:
        """Return the raw (still-encrypted) credential column, or None if
        unconfigured or no credential was ever set. Bypasses LokiConfigRead
        entirely — mirrors CloudflareAccountRepository.get_token_ciphertext,
        same reasoning: a secret never enters the safe Read schema."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        environment_id: UUID,
        endpoint_url: str,
        tenant_id: str | None,
        auth_type: LokiAuthType,
        credential: str | None,
        default_query: str,
        default_range_minutes: int,
    ) -> LokiConfigRead:
        """Create a new config. Caller must confirm no existing config for this environment first."""
        raise NotImplementedError

    @abstractmethod
    async def update_by_environment_id(
        self,
        environment_id: UUID,
        *,
        endpoint_url: str,
        tenant_id: str | None,
        auth_type: LokiAuthType,
        credential: str | None,
        default_query: str,
        default_range_minutes: int,
    ) -> LokiConfigRead:
        """Overwrite an environment's config with the given values."""
        raise NotImplementedError

    @abstractmethod
    async def delete_by_environment_id(self, environment_id: UUID) -> None:
        """Remove an environment's config."""
        raise NotImplementedError


class LokiConfigRepository(AbstractLokiConfigRepository):
    """SQLAlchemy implementation. No cache-aside — same low-traffic,
    high-mutation reasoning as CloudflareConfigRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    @helper
    def _to_read(row: LokiConfig) -> LokiConfigRead:
        """LokiConfigRead never carries the raw credential, only whether one is
        set — a derived field with no matching ORM attribute, so plain
        model_validate(row) can't produce it the way it does for every other
        Read schema in this codebase."""
        return LokiConfigRead(
            id=row.id,
            environment_id=row.environment_id,
            endpoint_url=row.endpoint_url,
            tenant_id=row.tenant_id,
            auth_type=row.auth_type,
            has_credential=row.credential is not None,
            default_query=row.default_query,
            default_range_minutes=row.default_range_minutes,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @database
    async def get_by_id(self, entity_id: UUID) -> LokiConfigRead | None:
        row = await self._session.get(LokiConfig, entity_id)
        return self._to_read(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[LokiConfigRead], int]:
        """Required by AbstractRepository; configs are looked up per-environment in practice."""
        rows = await self._session.scalars(
            select(LokiConfig).order_by(LokiConfig.id).limit(limit).offset(offset)
        )
        items = [self._to_read(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(LokiConfig))
        return items, total or 0

    @database
    async def get_by_environment_id(self, environment_id: UUID) -> LokiConfigRead | None:
        row = await self._session.scalar(
            select(LokiConfig).where(LokiConfig.environment_id == environment_id)
        )
        return self._to_read(row) if row else None

    @database
    async def get_credential_ciphertext(self, environment_id: UUID) -> str | None:
        row = await self._session.scalar(
            select(LokiConfig).where(LokiConfig.environment_id == environment_id)
        )
        return row.credential if row is not None else None

    @database
    async def create(
        self,
        *,
        environment_id: UUID,
        endpoint_url: str,
        tenant_id: str | None,
        auth_type: LokiAuthType,
        credential: str | None,
        default_query: str,
        default_range_minutes: int,
    ) -> LokiConfigRead:
        row = LokiConfig(
            environment_id=environment_id,
            endpoint_url=endpoint_url,
            tenant_id=tenant_id,
            auth_type=auth_type,
            credential=credential,
            default_query=default_query,
            default_range_minutes=default_range_minutes,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_read(row)

    @database
    async def update_by_environment_id(
        self,
        environment_id: UUID,
        *,
        endpoint_url: str,
        tenant_id: str | None,
        auth_type: LokiAuthType,
        credential: str | None,
        default_query: str,
        default_range_minutes: int,
    ) -> LokiConfigRead:
        row = await self._session.scalar(
            select(LokiConfig).where(LokiConfig.environment_id == environment_id)
        )
        if row is None:
            raise ValueError(f"loki config for environment {environment_id} does not exist")
        row.endpoint_url = endpoint_url
        row.tenant_id = tenant_id
        row.auth_type = auth_type
        row.credential = credential
        row.default_query = default_query
        row.default_range_minutes = default_range_minutes
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_read(row)

    @database
    async def delete_by_environment_id(self, environment_id: UUID) -> None:
        row = await self._session.scalar(
            select(LokiConfig).where(LokiConfig.environment_id == environment_id)
        )
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

