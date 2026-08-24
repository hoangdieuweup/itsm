"""SQLAlchemy models owned exclusively by the observability module. No other
module may query these tables directly — reach them only through
app.modules.observability.public (currently empty; add a facade method here
if a real cross-module consumer appears)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.observability.constants import (
    AlertingLimits,
    AlertRuleSource,
    AlertSeverity,
    IncidentCategory,
    IncidentSource,
    IncidentStatus,
    LokiAuthType,
    ObservabilityDefaults,
    ObservabilityLimits,
)


class LokiConfig(Base):
    """A single environment's Loki connection settings. 1:1 per environment —
    UNIQUE on environment_id, same convention as CloudflareConfig."""

    __tablename__ = "loki_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), unique=True
    )
    endpoint_url: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[str | None] = mapped_column(
        String(ObservabilityLimits.MAX_TENANT_ID_LENGTH), nullable=True
    )
    auth_type: Mapped[LokiAuthType] = mapped_column(Enum(LokiAuthType, native_enum=False))
    credential: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_query: Mapped[str] = mapped_column(Text, default="")
    default_range_minutes: Mapped[int] = mapped_column(
        Integer, default=ObservabilityDefaults.DEFAULT_RANGE_MINUTES
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AlertRule(Base):
    """A rule defining when to raise an incident, per environment. Either
    mirrors a Cloudflare Notification Policy (CLOUDFLARE_NATIVE) or a
    LogQL/threshold rule evaluated by Loki's own Ruler (LOKI_QUERY)."""

    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(AlertingLimits.MAX_NAME_LENGTH))
    source: Mapped[AlertRuleSource] = mapped_column(Enum(AlertRuleSource, native_enum=False))
    cf_alert_type: Mapped[str | None] = mapped_column(
        String(AlertingLimits.MAX_CF_ALERT_TYPE_LENGTH), nullable=True
    )
    cf_policy_id: Mapped[str | None] = mapped_column(
        String(AlertingLimits.MAX_CF_POLICY_ID_LENGTH), nullable=True, index=True
    )
    condition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity, native_enum=False))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AlertRuleChannel(Base):
    """Bridge table: which notification channels fire when an alert rule triggers."""

    __tablename__ = "alert_rule_channels"

    alert_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_channels.id", ondelete="CASCADE"), primary_key=True
    )


class Incident(Base):
    """A business record of a detected or manually-filed incident. Lifecycle:
    OPEN -> ACKNOWLEDGED -> RESOLVED (see IncidentRules.validate_transition)."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="RESTRICT"), index=True
    )
    alert_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[IncidentSource] = mapped_column(Enum(IncidentSource, native_enum=False))
    category: Mapped[IncidentCategory] = mapped_column(Enum(IncidentCategory, native_enum=False))
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity, native_enum=False))
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False), default=IncidentStatus.OPEN
    )
    title: Mapped[str] = mapped_column(String(AlertingLimits.MAX_TITLE_LENGTH))
    log_ref_id: Mapped[str | None] = mapped_column(
        String(AlertingLimits.MAX_LOG_REF_ID_LENGTH), nullable=True
    )
    alert_correlation_id: Mapped[str | None] = mapped_column(
        String(AlertingLimits.MAX_CORRELATION_ID_LENGTH), nullable=True, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
