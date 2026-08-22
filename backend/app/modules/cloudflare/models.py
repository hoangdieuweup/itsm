"""ORM models owned by the cloudflare module. No other module may query these tables."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountLimits


class CloudflareAccount(Base):
    """A Cloudflare account credential, potentially shared across many projects."""

    __tablename__ = "cloudflare_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(CloudflareAccountLimits.MAX_LABEL_LENGTH))
    cf_account_id: Mapped[str] = mapped_column(String(CloudflareAccountLimits.MAX_CF_ACCOUNT_ID_LENGTH))
    api_token: Mapped[str] = mapped_column(Text)
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
