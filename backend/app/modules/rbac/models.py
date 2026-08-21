"""ORM models owned by the rbac module. No other module may query these tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.rbac.constants import RbacLimits


class Role(Base):
    """A named bundle of permissions. is_system roles are seeded and undeletable/unrenamable."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
    """One (resource, action) pair. A fixed catalog the app defines, not admin-invented."""

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("resource", "action", name="permissions_resource_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(255))


class RolePermission(Base):
    """The role -> permission matrix."""

    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    """A user's single role grant. user_id is the primary key: one active role
    per user in this single-tenant design — see spec's Scope > Out."""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True)
