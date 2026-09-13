"""Single access path to the alert_rules and alert_rule_channels tables."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.modules.observability.constants import (
    AlertRuleSource,
    AlertSeverity,
)
from app.modules.observability.exceptions import AlertRuleNotFound
from app.modules.observability.models import AlertRule, AlertRuleChannel
from app.modules.observability.schemas import AlertRuleRead


class AbstractAlertRuleRepository(AbstractRepository[AlertRuleRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def get_by_cf_policy_id(self, cf_policy_id: str) -> AlertRuleRead | None:
        """Exact-match lookup — the webhook receiver's join key (Decision #4)."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_environment(self, environment_id: UUID) -> list[AlertRuleRead]:
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        environment_id: UUID,
        name: str,
        source: AlertRuleSource,
        cf_alert_type: str | None = None,
        condition: dict | None = None,
        severity: AlertSeverity,
    ) -> AlertRuleRead:
        raise NotImplementedError

    @abstractmethod
    async def set_cf_policy_id(self, alert_rule_id: UUID, *, cf_policy_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def update(
        self,
        alert_rule_id: UUID,
        *,
        name: str | None = None,
        is_active: bool | None = None,
        severity: AlertSeverity | None = None,
    ) -> AlertRuleRead:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, alert_rule_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_channel_ids(self, alert_rule_id: UUID) -> list[UUID]:
        raise NotImplementedError

    @abstractmethod
    async def set_channels(self, alert_rule_id: UUID, channel_ids: list[UUID]) -> None:
        raise NotImplementedError


class AlertRuleRepository(AbstractAlertRuleRepository):
    """SQLAlchemy implementation. No cache-aside — same low-traffic,
    high-mutation reasoning as CloudflareConfigRepository/LokiConfigRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> AlertRuleRead | None:
        row = await self._session.get(AlertRule, entity_id)
        return await self._to_read(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[AlertRuleRead], int]:
        """Required by AbstractRepository; alert rules are looked up per-environment in practice."""
        rows = await self._session.scalars(
            select(AlertRule).order_by(AlertRule.created_at).limit(limit).offset(offset)
        )
        items = [await self._to_read(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(AlertRule))
        return items, total or 0

    @database
    async def get_by_cf_policy_id(self, cf_policy_id: str) -> AlertRuleRead | None:
        row = await self._session.scalar(select(AlertRule).where(AlertRule.cf_policy_id == cf_policy_id))
        return await self._to_read(row) if row else None

    @database
    async def list_for_environment(self, environment_id: UUID) -> list[AlertRuleRead]:
        rows = await self._session.scalars(
            select(AlertRule).where(AlertRule.environment_id == environment_id).order_by(AlertRule.created_at)
        )
        return [await self._to_read(row) for row in rows]

    @database
    async def create(
        self,
        *,
        environment_id: UUID,
        name: str,
        source: AlertRuleSource,
        cf_alert_type: str | None = None,
        condition: dict | None = None,
        severity: AlertSeverity,
    ) -> AlertRuleRead:
        row = AlertRule(
            environment_id=environment_id,
            name=name,
            source=source,
            cf_alert_type=cf_alert_type,
            condition=condition,
            severity=severity,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return await self._to_read(row)

    @database
    async def set_cf_policy_id(self, alert_rule_id: UUID, *, cf_policy_id: str) -> None:
        row = await self._session.get(AlertRule, alert_rule_id)
        if row is None:
            raise AlertRuleNotFound()
        row.cf_policy_id = cf_policy_id
        await self._session.flush()

    @database
    async def update(
        self,
        alert_rule_id: UUID,
        *,
        name: str | None = None,
        is_active: bool | None = None,
        severity: AlertSeverity | None = None,
    ) -> AlertRuleRead:
        row = await self._session.get(AlertRule, alert_rule_id)
        if row is None:
            raise AlertRuleNotFound()
        if name is not None:
            row.name = name
        if is_active is not None:
            row.is_active = is_active
        if severity is not None:
            row.severity = severity
        await self._session.flush()
        await self._session.refresh(row)
        return await self._to_read(row)

    @database
    async def delete(self, alert_rule_id: UUID) -> None:
        row = await self._session.get(AlertRule, alert_rule_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def list_channel_ids(self, alert_rule_id: UUID) -> list[UUID]:
        rows = await self._session.scalars(
            select(AlertRuleChannel.channel_id).where(AlertRuleChannel.alert_rule_id == alert_rule_id)
        )
        return list(rows)

    @database
    async def set_channels(self, alert_rule_id: UUID, channel_ids: list[UUID]) -> None:
        await self._session.execute(
            delete(AlertRuleChannel).where(AlertRuleChannel.alert_rule_id == alert_rule_id)
        )
        for channel_id in channel_ids:
            self._session.add(AlertRuleChannel(alert_rule_id=alert_rule_id, channel_id=channel_id))
        await self._session.flush()

    @helper
    async def _to_read(self, row: AlertRule) -> AlertRuleRead:
        channel_ids = await self.list_channel_ids(row.id)
        return AlertRuleRead(
            id=row.id,
            environment_id=row.environment_id,
            name=row.name,
            source=row.source,
            cf_alert_type=row.cf_alert_type,
            cf_policy_id=row.cf_policy_id,
            condition=row.condition,
            severity=row.severity,
            is_active=row.is_active,
            channel_ids=channel_ids,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
