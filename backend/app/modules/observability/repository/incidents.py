"""Single access path to the incidents table."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.observability.constants import (
    AlertSeverity,
    IncidentCategory,
    IncidentSource,
    IncidentStatus,
)
from app.modules.observability.exceptions import IncidentNotFound
from app.modules.observability.models import Incident
from app.modules.observability.schemas import IncidentRead


class AbstractIncidentRepository(AbstractRepository[IncidentRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def get_open_by_correlation_id(self, correlation_id: str) -> IncidentRead | None:
        """Backs the dedup guard in the webhook receivers (Decision #4/#11) —
        excludes RESOLVED so a since-cleared alert can re-open a fresh incident."""
        raise NotImplementedError

    @abstractmethod
    async def list_page_filtered(
        self,
        *,
        project_id: UUID | None = None,
        environment_id: UUID | None = None,
        status: IncidentStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[IncidentRead], int]:
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        project_id: UUID,
        environment_id: UUID,
        alert_rule_id: UUID | None,
        source: IncidentSource,
        category: IncidentCategory,
        severity: AlertSeverity,
        title: str,
        alert_correlation_id: str | None = None,
        log_ref_id: str | None = None,
    ) -> IncidentRead:
        raise NotImplementedError

    @abstractmethod
    async def update_status(
        self, incident_id: UUID, *, status: IncidentStatus, actor_id: UUID | None, at
    ) -> IncidentRead:
        raise NotImplementedError


class IncidentRepository(AbstractIncidentRepository):
    """SQLAlchemy implementation. No cache-aside — incidents are a
    frequently-mutated, always-fresh-wanted business record."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> IncidentRead | None:
        row = await self._session.get(Incident, entity_id)
        return IncidentRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[IncidentRead], int]:
        """Required by AbstractRepository; incidents are looked up via list_page_filtered in practice."""
        return await self.list_page_filtered(limit=limit, offset=offset)

    @database
    async def get_open_by_correlation_id(self, correlation_id: str) -> IncidentRead | None:
        row = await self._session.scalar(
            select(Incident).where(
                Incident.alert_correlation_id == correlation_id, Incident.status != IncidentStatus.RESOLVED
            )
        )
        return IncidentRead.model_validate(row) if row else None

    @database
    async def list_page_filtered(
        self,
        *,
        project_id: UUID | None = None,
        environment_id: UUID | None = None,
        status: IncidentStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[IncidentRead], int]:
        stmt = select(Incident)
        if project_id is not None:
            stmt = stmt.where(Incident.project_id == project_id)
        if environment_id is not None:
            stmt = stmt.where(Incident.environment_id == environment_id)
        if status is not None:
            stmt = stmt.where(Incident.status == status)
        stmt = stmt.order_by(Incident.detected_at.desc()).limit(limit).offset(offset)
        rows = await self._session.scalars(stmt)
        items = [IncidentRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        return items, total or 0

    @database
    async def create(
        self,
        *,
        project_id: UUID,
        environment_id: UUID,
        alert_rule_id: UUID | None,
        source: IncidentSource,
        category: IncidentCategory,
        severity: AlertSeverity,
        title: str,
        alert_correlation_id: str | None = None,
        log_ref_id: str | None = None,
    ) -> IncidentRead:
        row = Incident(
            project_id=project_id,
            environment_id=environment_id,
            alert_rule_id=alert_rule_id,
            source=source,
            category=category,
            severity=severity,
            title=title,
            alert_correlation_id=alert_correlation_id,
            log_ref_id=log_ref_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return IncidentRead.model_validate(row)

    @database
    async def update_status(
        self, incident_id: UUID, *, status: IncidentStatus, actor_id: UUID | None, at
    ) -> IncidentRead:
        row = await self._session.get(Incident, incident_id)
        if row is None:
            raise IncidentNotFound()
        row.status = status
        if status == IncidentStatus.ACKNOWLEDGED:
            row.acknowledged_at, row.acknowledged_by = at, actor_id
        elif status == IncidentStatus.RESOLVED:
            row.resolved_at, row.resolved_by = at, actor_id
        await self._session.flush()
        await self._session.refresh(row)
        return IncidentRead.model_validate(row)
