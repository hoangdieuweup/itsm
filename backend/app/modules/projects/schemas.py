"""Schemas for the projects module."""

from datetime import datetime
from uuid import UUID

from app.core.models import CustomModel, FrozenModel
from app.modules.projects.constants import EnvironmentType, ProjectLinkType


class ProjectRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: UUID
    name: str
    description: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ProjectCreate(CustomModel):
    """Request body for POST /projects."""

    name: str
    description: str | None = None


class ProjectUpdate(CustomModel):
    """Request body for PATCH /projects/{id}. None means unchanged."""

    name: str | None = None
    description: str | None = None


class EnvironmentRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: UUID
    project_id: UUID
    type: EnvironmentType
    name: str
    base_url: str | None = None
    created_at: datetime
    updated_at: datetime


class EnvironmentCreate(CustomModel):
    """Request body for POST /projects/{project_id}/environments."""

    type: EnvironmentType
    name: str
    base_url: str | None = None


class EnvironmentUpdate(CustomModel):
    """Request body for PATCH /environments/{id}. type is immutable — the
    UNIQUE(project_id, type) constraint models a fixed tier, not a renameable one."""

    name: str | None = None
    base_url: str | None = None


class ProjectLinkRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: UUID
    project_id: UUID
    type: ProjectLinkType
    name: str
    url: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ProjectLinkCreate(CustomModel):
    """Request body for POST /projects/{project_id}/links."""

    type: ProjectLinkType
    name: str
    url: str


class ProjectLinkUpdate(CustomModel):
    """Request body for PATCH /links/{id}."""

    name: str | None = None
    url: str | None = None
