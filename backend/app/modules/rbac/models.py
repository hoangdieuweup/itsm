"""ORM models owned by the rbac module. No other module may query these tables."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.rbac.constants import RbacLimits


class Role(Base):
    """A named bundle of permissions. is_system roles are seeded and undeletable/unrenamable."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(RbacLimits.MAX_ROLE_NAME_LENGTH), unique=True, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", lazy="noload", viewonly=True
    )


class Permission(Base):
    """One (resource, action) pair. A fixed catalog the app defines, not admin-invented.

    description_key is an i18n message key (e.g. "permissions.role.create"),
    not display text — the frontend translates it, the same way
    ErrorPayload.code is a key, not a message. See the nextjs-modular-
    architecture skill's references/i18n-and-errors.md for the pattern this
    mirrors.
    """

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("resource", "action", name="permissions_resource_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    description_key: Mapped[str] = mapped_column(String(255))


class RolePermission(Base):
    """The role -> permission matrix."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    """A user's role grant. Composite PK (user_id, role_id) allows multiple roles per user."""

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
