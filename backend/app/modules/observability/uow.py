"""Transaction boundary for the observability module."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.uow import AbstractUnitOfWork
from app.core.uow import SqlAlchemyUnitOfWork
from app.modules.observability.repository import (
    AbstractAlertRuleRepository,
    AbstractIncidentRepository,
    AbstractLokiConfigRepository,
    AlertRuleRepository,
    IncidentRepository,
    LokiConfigRepository,
)


class AbstractObservabilityUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    loki_configs: AbstractLokiConfigRepository
    alert_rules: AbstractAlertRuleRepository
    incidents: AbstractIncidentRepository


class ObservabilityUnitOfWork(AbstractObservabilityUnitOfWork, SqlAlchemyUnitOfWork):
    """Owns the transaction for the observability module's tables. No cache
    invalidation plumbing (unlike cloudflare/projects) — none of loki_configs,
    alert_rules, or incidents have a cache-aside repository (Decision #9:
    low-traffic-or-high-mutation reads, premature caching adds complexity
    with no measured benefit)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.loki_configs = LokiConfigRepository(session)
        self.alert_rules = AlertRuleRepository(session)
        self.incidents = IncidentRepository(session)
