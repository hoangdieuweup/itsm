"""ORM models owned by the cloudflare module. No other module may query these tables."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.cloudflare.constants import (
    AccessLevel,
    CloudflareAccountLimits,
    DnsRecordType,
    LogSource,
    ManagedBy,
    TunnelStatus,
)


class CloudflareAccount(Base):
    """A Cloudflare account credential, potentially shared across many projects."""

    __tablename__ = "cloudflare_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(CloudflareAccountLimits.MAX_LABEL_LENGTH))
    cf_account_id: Mapped[str] = mapped_column(String(CloudflareAccountLimits.MAX_CF_ACCOUNT_ID_LENGTH))
    api_token: Mapped[str] = mapped_column(Text)
    cf_webhook_destination_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    webhook_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CloudflareAccountManager(Base):
    """Per-account ACL row: one user's access_level on one cloudflare_account."""

    __tablename__ = "cloudflare_account_managers"

    cloudflare_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cloudflare_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    access_level: Mapped[AccessLevel] = mapped_column(Enum(AccessLevel, native_enum=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CloudflareConfig(Base):
    """One environment's binding to a Cloudflare account + zone. UNIQUE on
    environment_id — an environment has at most one binding."""

    __tablename__ = "cloudflare_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), unique=True
    )
    cloudflare_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cloudflare_accounts.id", ondelete="RESTRICT")
    )
    zone_id: Mapped[str] = mapped_column(String(64))
    zone_name: Mapped[str] = mapped_column(String(255))
    log_source: Mapped[LogSource] = mapped_column(
        Enum(LogSource, native_enum=False), default=LogSource.AUDIT_LOG
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DnsRecord(Base):
    """One DNS record this app knows about for an environment."""

    __tablename__ = "dns_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), index=True, nullable=True
    )
    cf_record_id: Mapped[str] = mapped_column(String(64), unique=True)
    record_type: Mapped[DnsRecordType] = mapped_column(Enum(DnsRecordType, native_enum=False))
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proxied: Mapped[bool] = mapped_column(Boolean, default=False)
    ttl: Mapped[int] = mapped_column(Integer, default=1)
    managed_by: Mapped[ManagedBy] = mapped_column(
        Enum(ManagedBy, native_enum=False), default=ManagedBy.SYSTEM
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CloudflareTunnel(Base):
    """A Cloudflare Tunnel, scoped to the account it belongs to on Cloudflare.
    A tunnel is an account-level resource that commonly serves many
    environments/projects at once through different public hostnames — see
    TunnelPublicHostname.environment_id for the actual per-environment
    scoping point."""

    __tablename__ = "cloudflare_tunnels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cloudflare_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cloudflare_accounts.id", ondelete="CASCADE"), index=True
    )
    cf_tunnel_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[TunnelStatus] = mapped_column(
        Enum(TunnelStatus, native_enum=False), default=TunnelStatus.UNKNOWN
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TunnelPublicHostname(Base):
    """One public hostname (ingress rule) published through a Tunnel. Only
    hostname+service are persisted (Decision #2) — path/originRequest live
    only in Cloudflare's own ingress array, never modeled here.

    environment_id is the actual per-environment scoping point (a tunnel
    itself is account-scoped, see CloudflareTunnel) — nullable because a
    hostname only matches an environment when that environment has a
    base_url that exactly matches it; an unmatched hostname (or one on an
    environment with no base_url configured) has environment_id=None."""

    __tablename__ = "tunnel_public_hostnames"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tunnel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cloudflare_tunnels.id", ondelete="CASCADE"), index=True
    )
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    hostname: Mapped[str] = mapped_column(String(255), unique=True)
    service: Mapped[str] = mapped_column(String(255))
    managed_by: Mapped[ManagedBy] = mapped_column(
        Enum(ManagedBy, native_enum=False), default=ManagedBy.SYSTEM
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
