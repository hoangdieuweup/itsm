"""SQLAlchemy models owned exclusively by the observability module. No other
module may query these tables directly — reach them only through
app.modules.observability.public (currently empty; add a facade method here
if a real cross-module consumer appears)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.observability.constants import LokiAuthType, ObservabilityLimits


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
    default_range_minutes: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
