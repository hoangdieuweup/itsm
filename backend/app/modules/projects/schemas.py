"""Schemas for the projects module."""

from datetime import datetime
from uuid import UUID

from app.core.models import CustomModel, FrozenModel
from app.modules.projects.constants import EnvironmentType, ProjectLinkType
from app.modules.rbac.public import PermissionRead
from app.modules.users.public import UserRead


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


class ProjectMemberRead(FrozenModel):
    """A project member enriched with the target user's email/name — the
    repository only knows user_id, resolving identity is the use case's job."""

    user_id: UUID
    name: str
    email: str
    created_at: datetime
    project_role_id: UUID | None = None
    project_role_name: str | None = None


class ProjectMemberCreate(CustomModel):
    """Request body for POST /projects/{project_id}/members."""

    user_id: UUID


class ProjectRoleRead(FrozenModel):
    """A project role together with the permissions currently granted to it."""

    id: UUID
    project_id: UUID
    name: str
    permissions: list[PermissionRead]
    created_at: datetime
    updated_at: datetime


class ProjectRoleCreate(CustomModel):
    """Request body for POST /projects/{project_id}/roles."""

    name: str
    permission_ids: list[UUID] = []


class ProjectRoleUpdate(CustomModel):
    """Request body for PATCH /project-roles/{id}. None means unchanged."""

    name: str | None = None
    permission_ids: list[UUID] | None = None


class ProjectMemberRoleAssign(CustomModel):
    """Request body for PUT /projects/{project_id}/members/{user_id}/role.
    None clears the member's project role (reverts to global-only)."""

    project_role_id: UUID | None


class ProjectPermissionSetRead(FrozenModel):
    """Response body for GET /projects/{project_id}/permissions — the
    caller's own effective 'resource.action' set in this project."""

    project_id: UUID
    permissions: list[str]


class ProjectPermissionGrant(FrozenModel):
    """The caller's resolved, effective 'resource.action' set inside one
    project — global permissions UNIONed with their project role's grants,
    bounded by ProjectScopedPermissionCatalog.ASSIGNABLE on the way IN
    (enforced when a role is created/updated), not here."""

    user: UserRead
    project_id: UUID
    permissions: frozenset[str]
