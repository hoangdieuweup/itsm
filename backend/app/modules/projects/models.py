"""ORM models owned by the projects module. No other module may query these tables."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.projects.constants import EnvironmentType, ProjectLimits, ProjectLinkType


class Project(Base):
    """A project, grouping environments and external links."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(ProjectLimits.MAX_NAME_LENGTH))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectLink(Base):
    """An external link (Jira/Git/other) attached to a project."""

    __tablename__ = "project_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[ProjectLinkType] = mapped_column(Enum(ProjectLinkType, native_enum=False))
    name: Mapped[str] = mapped_column(String(ProjectLimits.MAX_LINK_NAME_LENGTH))
    url: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Environment(Base):
    """A DEV/STAGING/PRODUCTION deployment tier of a project. At most one per type per project."""

    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "type", name="environments_project_id_type_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[EnvironmentType] = mapped_column(Enum(EnvironmentType, native_enum=False))
    name: Mapped[str] = mapped_column(String(ProjectLimits.MAX_ENVIRONMENT_NAME_LENGTH))
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectMember(Base):
    """Binary project membership: a user must have a row here (or hold the
    project:manage_all bypass) to see or act on a project and its
    environments/links. No access-level column — this is deliberately not a
    tiered ACL like CloudflareAccountManager."""

    __tablename__ = "project_members"
    __table_args__ = (PrimaryKeyConstraint("project_id", "user_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_roles.id", ondelete="SET NULL"), nullable=True
    )


class ProjectRole(Base):
    """A role scoped to exactly one project — an assignable bundle of the
    global permission catalog's atoms, restricted at the service layer to
    ProjectScopedPermissionCatalog.ASSIGNABLE."""

    __tablename__ = "project_roles"
    __table_args__ = (UniqueConstraint("project_id", "name", name="project_roles_project_id_name_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(ProjectLimits.MAX_PROJECT_ROLE_NAME_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectRolePermission(Base):
    """The project_role -> permission matrix. permission_id FKs the rbac
    module's `permissions` table by table name only — no Python import of
    app.modules.rbac anywhere in this file."""

    __tablename__ = "project_role_permissions"
    __table_args__ = (PrimaryKeyConstraint("project_role_id", "permission_id"),)

    project_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_roles.id", ondelete="CASCADE")
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE")
    )
