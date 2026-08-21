"""Schemas for the rbac module."""

from app.core.models import FrozenModel


class PermissionRead(FrozenModel):
    """Representation safe to round trip through the cache."""

    id: int
    resource: str
    action: str
    description: str


class RoleRead(FrozenModel):
    """A role together with the permissions currently granted to it."""

    id: int
    name: str
    is_system: bool
    permissions: list[PermissionRead]


class RoleCreate(FrozenModel):
    """Request body for POST /rbac/roles."""

    name: str
    permission_ids: list[int] = []


class RoleUpdate(FrozenModel):
    """Request body for PATCH /rbac/roles/{id}. name=None leaves the name unchanged;
    permission_ids=None leaves the permission set unchanged — this is how a system
    role's permissions stay editable while its name stays locked (see rules.py)."""

    name: str | None = None
    permission_ids: list[int] | None = None


class RoleSummary(FrozenModel):
    """What auth/me composes into the session: role name + flat permission strings."""

    role_name: str
    permissions: list[str]


class RoleAssignment(FrozenModel):
    """Request body for PATCH /rbac/users/{id}/role."""

    role_id: int
