from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.models import CustomModel, FrozenModel
from app.integrations.loki.schemas import LokiLogEntry
from app.modules.observability.constants import LokiAuthType, ObservabilityLimits


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
