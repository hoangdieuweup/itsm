"""Schemas for the rbac module."""

from uuid import UUID

from app.core.models import FrozenModel


class PermissionRead(FrozenModel):
    """Representation safe to round trip through the cache.

    description_key is an i18n key, not display text — see Permission's
    own docstring in models.py.
    """

    id: UUID
    resource: str
    action: str
    description_key: str


class RoleRead(FrozenModel):
    """A role together with the permissions currently granted to it."""

    id: UUID
    name: str
    is_system: bool
    permissions: list[PermissionRead]


class RoleCreate(FrozenModel):
    """Request body for POST /rbac/roles."""

    name: str
    permission_ids: list[UUID] = []


class RoleUpdate(FrozenModel):
    """Request body for PATCH /rbac/roles/{id}. name=None leaves the name unchanged;
    permission_ids=None leaves the permission set unchanged — this is how a system
    role's permissions stay editable while its name stays locked (see rules.py)."""

    name: str | None = None
    permission_ids: list[UUID] | None = None


class RoleSummary(FrozenModel):
    """What auth/me composes into the session: role names + flat permission strings."""

    roles: list[str] = []
    permissions: list[str] = []
    role_name: str | None = None


class RoleAssignment(FrozenModel):
    """Request body for PUT /rbac/users/{id}/roles and backwards-compatible assignments."""

    role_ids: list[UUID] = []
    role_id: UUID | None = None


class UserRolesAssignment(FrozenModel):
    """Request body for PUT /rbac/users/{id}/roles."""

    role_ids: list[UUID]
