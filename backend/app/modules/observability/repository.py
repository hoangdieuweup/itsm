"""Single access path to the loki_configs, alert_rules, and incidents tables."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.modules.observability.constants import (
    AlertRuleSource,
    AlertSeverity,
    IncidentCategory,
    IncidentSource,
    IncidentStatus,
    LokiAuthType,
)
from app.modules.observability.models import AlertRule, AlertRuleChannel, Incident, LokiConfig
from app.modules.observability.schemas import AlertRuleRead, IncidentRead, LokiConfigRead


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
            raise ValueError(f"alert rule {alert_rule_id} does not exist")
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
            raise ValueError(f"alert rule {alert_rule_id} does not exist")
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
            raise ValueError(f"incident {incident_id} does not exist")
        row.status = status
        if status == IncidentStatus.ACKNOWLEDGED:
            row.acknowledged_at, row.acknowledged_by = at, actor_id
        elif status == IncidentStatus.RESOLVED:
            row.resolved_at, row.resolved_by = at, actor_id
        await self._session.flush()
        await self._session.refresh(row)
        return IncidentRead.model_validate(row)
