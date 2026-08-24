"""Transaction boundary for the observability module."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.modules.observability.repository import (
    AbstractAlertRuleRepository,
    AbstractIncidentRepository,
    AbstractLokiConfigRepository,
    AlertRuleRepository,
    IncidentRepository,
    LokiConfigRepository,
)

logger = logging.getLogger(__name__)


class AbstractObservabilityUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    loki_configs: AbstractLokiConfigRepository
    alert_rules: AbstractAlertRuleRepository
    incidents: AbstractIncidentRepository


class ObservabilityUnitOfWork(AbstractObservabilityUnitOfWork):
    """Owns the transaction for the observability module's tables. No cache
    invalidation plumbing (unlike cloudflare/projects) — none of loki_configs,
    alert_rules, or incidents have a cache-aside repository (Decision #9:
    low-traffic-or-high-mutation reads, premature caching adds complexity
    with no measured benefit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.loki_configs = LokiConfigRepository(session)
        self.alert_rules = AlertRuleRepository(session)
        self.incidents = IncidentRepository(session)

    @database
    async def commit(self) -> None:
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        await self._session.rollback()
        logger.warning("observability unit of work rolled back")
