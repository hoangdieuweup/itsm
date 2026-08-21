"""ORM models owned by the projects module. No other module may query these tables."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
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
