from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.models import CustomModel, FrozenModel
from app.integrations.loki.schemas import LokiLogEntry
from app.modules.observability.constants import (
    AlertingLimits,
    AlertRuleSource,
    AlertSeverity,
    IncidentCategory,
    IncidentSource,
    IncidentStatus,
    LokiAuthType,
    ObservabilityLimits,
)


class LokiConfigRead(FrozenModel):
    id: UUID
    environment_id: UUID
    endpoint_url: str
    tenant_id: str | None
    auth_type: LokiAuthType
    has_credential: bool
    default_query: str
    default_range_minutes: int
    created_at: datetime
    updated_at: datetime


class LokiConfigCreate(CustomModel):
    endpoint_url: str = Field(max_length=ObservabilityLimits.MAX_ENDPOINT_URL_LENGTH)
    tenant_id: str | None = Field(default=None, max_length=ObservabilityLimits.MAX_TENANT_ID_LENGTH)
    auth_type: LokiAuthType
    credential: str | None = None
    default_query: str = Field(default="", max_length=ObservabilityLimits.MAX_QUERY_LENGTH)
    default_range_minutes: int = 60


class LokiConfigUpdate(CustomModel):
    endpoint_url: str | None = Field(default=None, max_length=ObservabilityLimits.MAX_ENDPOINT_URL_LENGTH)
    tenant_id: str | None = Field(default=None, max_length=ObservabilityLimits.MAX_TENANT_ID_LENGTH)
    auth_type: LokiAuthType | None = None
    credential: str | None = None
    default_query: str | None = Field(default=None, max_length=ObservabilityLimits.MAX_QUERY_LENGTH)
    default_range_minutes: int | None = None


class LogQueryRequest(CustomModel):
    query: str = Field(max_length=ObservabilityLimits.MAX_QUERY_LENGTH)
    start: datetime
    end: datetime
    limit: int = ObservabilityLimits.DEFAULT_QUERY_LIMIT


class LogQueryResponse(FrozenModel):
    entries: list[LokiLogEntry]


class AvailableAlertOption(FrozenModel):
    alert_type: str
    display_name: str


class AlertRuleRead(FrozenModel):
    id: UUID
    environment_id: UUID
    name: str
    source: AlertRuleSource
    cf_alert_type: str | None
    cf_policy_id: str | None
    condition: dict | None
    severity: AlertSeverity
    is_active: bool
    channel_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class AlertRuleCreate(CustomModel):
    name: str = Field(max_length=AlertingLimits.MAX_NAME_LENGTH)
    source: AlertRuleSource
    cf_alert_type: str | None = None
    condition: dict | None = None
    severity: AlertSeverity
    channel_ids: list[UUID] = Field(default_factory=list)


class AlertRuleUpdate(CustomModel):
    name: str | None = Field(default=None, max_length=AlertingLimits.MAX_NAME_LENGTH)
    is_active: bool | None = None
    severity: AlertSeverity | None = None
    channel_ids: list[UUID] | None = None


class IncidentRead(FrozenModel):
    id: UUID
    project_id: UUID
    environment_id: UUID
    alert_rule_id: UUID | None
    source: IncidentSource
    category: IncidentCategory
    severity: AlertSeverity
    status: IncidentStatus
    title: str
    log_ref_id: str | None
    detected_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: UUID | None
    resolved_at: datetime | None
    resolved_by: UUID | None
    created_at: datetime
    updated_at: datetime


class CreateManualIncidentRequest(CustomModel):
    environment_id: UUID
    category: IncidentCategory
    severity: AlertSeverity
    title: str = Field(max_length=AlertingLimits.MAX_TITLE_LENGTH)
