# Advanced Permissions — Backend (RBAC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, testable RBAC backend — new `app/modules/rbac/` module (roles, permissions, `require_permission`), `auth` module cleanup (drop `Department`/`UserRole` enum/`RoleMapping`), and the admin API surface — with no frontend dependency. Verifiable end to end via `pytest` and the OpenAPI schema alone.

**Architecture:** New `app/modules/rbac/` module owning `roles`/`permissions`/`role_permissions`/`user_roles`, depending on `auth`'s `public.py` facade (never the reverse). `auth` drops its `role` column entirely; a user's role now lives only in `rbac.user_roles`. Single-tenant: no `organization_id` anywhere. One role per user (`user_roles.user_id` is the primary key).

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, Pydantic v2, pytest + testcontainers (Postgres), following `fastapi-modular-scaffold`.

**Spec:** `docs/superpowers/specs/2026-08-20-advanced-permissions-design.md` (backend half only — read it for the "why," this plan is the "how." Note: the spec's example table names are singular per the governing skill's illustration; this plan uses plural — `roles`/`permissions`/`role_permissions`/`user_roles` — to match this project's own existing convention, `departments`/`users`/`dx_tokens`. Same schema shape, just naming.)

## Global Constraints

- Every schema inherits `CustomModel`/`FrozenModel` (camelCase wire format).
- Every endpoint returns `ApiResponse[...]`.
- `repository.py`/`uow.py`/`services/*.py` extend the root `Abstract*` contracts (rule #15); constructors depend on the `Abstract*` type, never the concrete class, except in `dependencies.py`.
- No bare constant/helper outside a class in `constants.py`/`rules.py`/`utils/` (rule #16); `router.py`/`dependencies.py`/`public.py` stay plain FastAPI-callable functions.
- **Router thinness (rule #10, actively enforced per `reviewing-code-against-skills` update 2026-08-20):** every router function only translates HTTP → use-case call. No embedded formatting/redirect/cookie logic.
- Cross-module reads only through `public.py`, composed in the service/router layer — never a SQL join across module boundaries.
- Permission checks always go through `require_permission(resource, action)` — never `if user.role == "..."`.
- GitNexus MCP tools (`impact`/`detect_changes`/`check`) are **not connected in this session**. Task 10 (auth cleanup) is manually impact-mapped below in lieu of `impact()` — every touch point was grepped for on 2026-08-20/21. If GitNexus becomes available before execution, re-run `impact()` on `AuthRules.resolve_role`, `UserRole`, `Department`, `IssueTokens.execute` before starting Task 10 and diff against the list below.

---

## Manual impact map (GitNexus substitute) for Task 10–12

Grepped 2026-08-21, `backend/app` + `backend/tests`, exhaustive for these symbols:

| Symbol removed | Every reference (must all be touched in Task 10–12) |
|---|---|
| `UserRole` enum | `models.py:9,34`, `rules.py:10`, `constants.py:11,79-82`, `schemas.py:6,23`, `repository.py:11,40,111`, `tests/auth/test_rules.py` (whole file), `tests/auth/test_services.py:21,59,69,269,294,303,316,327,390` |
| `RoleMapping` | `rules.py:10,22,27-29`, `constants.py:76-84` |
| `AuthRules.resolve_role` | `rules.py:19`, `services/sync_external_user.py:37`, `tests/auth/test_rules.py:19-21` |
| `User.role` column / `role=` kwarg | `models.py:34`, `repository.py:40,111,126`, `services/sync_external_user.py:41`, `services/issue_tokens.py:32` (JWT claim), `tests/auth/test_services.py` (multiple `UserRead(role=...)` constructions) |
| `Department` model + `department_id` | `models.py`, `schemas.py` (`DepartmentRead`), `uow.py`, `repository.py` (`AbstractDepartmentRepository`/`DepartmentRepository`), `services/sync_external_user.py`, `tests/auth/test_services.py` (`FakeDepartmentRepository`, department assertions), `tests/auth/test_router.py` (`_profile()`'s `department=` kwarg stays — that's `dx_core`'s `DxUserProfile`, untouched; only `auth`'s *consumption* of it is removed) |

Not touched (confirmed out of blast radius): `app/integrations/dx_core/*` (its `DxUserProfile.roles`/`.department` fields reflect the real DX API contract and stay defined, just no longer read by `auth`), `app/modules/auth/config.py`, `app/modules/auth/events.py`, `app/modules/auth/dependencies.py`'s `get_current_user`/`require_auth` (don't reference role today).

---

### Task 1: Alembic migration — drop `Department`/`role`, create `rbac` tables

Schema-only task; no unit-test cycle applies (matches this project's existing initial migration, which also has none) — verified instead by applying/rolling back against a real Postgres.

**Files:**
- Create: `backend/alembic/versions/20260821_1000_create_rbac_tables_drop_department.py`

**Interfaces:**
- Produces: tables `roles(id, name, is_system, created_at, updated_at)`, `permissions(id, resource, action, description)`, `role_permissions(role_id, permission_id)`, `user_roles(user_id, role_id)`. Drops `departments`, `users.department_id`, `users.role`.

- [ ] **Step 1: Write the migration**

```python
"""create rbac tables, drop department and user role

Revision ID: 9a1f3c6de072
Revises: 5ebc211a92a1
Create Date: 2026-08-21 10:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "9a1f3c6de072"
down_revision = "5ebc211a92a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("users_department_id_fkey"), "users", type_="foreignkey")
    op.drop_index(op.f("users_department_id_idx"), table_name="users")
    op.drop_column("users", "department_id")
    op.drop_column("users", "role")
    op.drop_index(op.f("departments_code_idx"), table_name="departments")
    op.drop_table("departments")

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("roles_pkey")),
    )
    op.create_index(op.f("roles_name_idx"), "roles", ["name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("permissions_pkey")),
        sa.UniqueConstraint("resource", "action", name=op.f("permissions_resource_key")),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("role_permissions_role_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("role_permissions_permission_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("role_permissions_pkey")),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("user_roles_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("user_roles_role_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("user_roles_pkey")),
    )
    op.create_index(op.f("user_roles_role_id_idx"), "user_roles", ["role_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("user_roles_role_id_idx"), table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_index(op.f("roles_name_idx"), table_name="roles")
    op.drop_table("roles")

    op.add_column("users", sa.Column("role", sa.String(length=20), nullable=True))
    op.execute("UPDATE users SET role = 'member'")
    op.alter_column("users", "role", nullable=False)
    op.add_column("users", sa.Column("department_id", sa.Integer(), nullable=True))
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("departments_pkey")),
    )
    op.create_index(op.f("departments_code_idx"), "departments", ["code"], unique=True)
    op.create_index(op.f("users_department_id_idx"), "users", ["department_id"], unique=False)
    op.create_foreign_key(
        op.f("users_department_id_fkey"), "users", "departments", ["department_id"], ["id"], ondelete="SET NULL"
    )
```

Note: downgrade's re-added `role` column is a simplified `String`, not the original native-`False` `Enum` — good enough to make `alembic downgrade` reversible for local dev without losing the ability to go back further; it is **not** meant to exactly restore the pre-migration schema (that data is gone once forward-migrated in production, which is expected for a rollback of a breaking schema change).

- [ ] **Step 2: Apply and verify**

Run: `cd backend && alembic upgrade head`
Expected: no errors; `\d roles`, `\d permissions`, `\d role_permissions`, `\d user_roles` in `psql` show the columns above; `\d users` no longer has `role`/`department_id`.

- [ ] **Step 3: Round-trip the downgrade**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: both succeed with no errors (per `checklist.md`'s "Downgrade tested at least once").

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/20260821_1000_create_rbac_tables_drop_department.py
git commit -m "feat(rbac): migration for roles/permissions tables, drop department and user role"
```

---

### Task 2: `rbac` constants + models

**Files:**
- Create: `backend/app/modules/rbac/__init__.py`
- Create: `backend/app/modules/rbac/constants.py`
- Create: `backend/app/modules/rbac/models.py`

**Interfaces:**
- Produces: `RbacPermissionCatalog.CATALOG: list[tuple[str, str, str]]`, `RbacDefaults.{OWNER_ROLE_NAME,ADMIN_ROLE_NAME,MEMBER_ROLE_NAME,SYSTEM_ROLE_NAMES,DEFAULT_ROLE_NAME}`, `ErrorCode` (rbac's own), ORM classes `Role`, `Permission`, `RolePermission`, `UserRole`.

- [ ] **Step 1: Write `__init__.py`**

```python
"""RBAC module: roles, permissions, and the require_permission dependency
every other module gates its endpoints with. See public.py for the only
import surface other modules may use."""
```

- [ ] **Step 2: Write `constants.py`**

```python
"""Constants and enums owned by the rbac module."""

from enum import StrEnum


class RbacPermissionCatalog:
    """The fixed (resource, action, description) catalog — seeded from code,
    never admin-created. See rbac/seeds and references/rbac.md's anti-pattern
    list: permissions are what the application *can* do, not free text."""

    CATALOG: list[tuple[str, str, str]] = [
        ("role", "create", "Create a new role"),
        ("role", "read", "View roles and their permissions"),
        ("role", "update", "Rename a role or change its permission set"),
        ("role", "delete", "Delete a custom role"),
        ("permission", "read", "View the permission catalog"),
        ("user", "read", "View the user list"),
        ("user", "update_status", "Block or unblock a user"),
        ("user", "assign_role", "Assign a role to a user"),
    ]


class RbacDefaults:
    """Seeded role names. See seeds/seed_rbac.py."""

    OWNER_ROLE_NAME = "owner"
    ADMIN_ROLE_NAME = "admin"
    MEMBER_ROLE_NAME = "member"
    SYSTEM_ROLE_NAMES = (OWNER_ROLE_NAME, ADMIN_ROLE_NAME, MEMBER_ROLE_NAME)
    DEFAULT_ROLE_NAME = MEMBER_ROLE_NAME


class RbacLimits:
    """Numeric limits owned by the rbac module."""

    MAX_ROLE_NAME_LENGTH = 100


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    ROLE_NOT_FOUND = "rbac_role_not_found"
    DUPLICATE_ROLE_NAME = "rbac_duplicate_role_name"
    SYSTEM_ROLE_IMMUTABLE = "rbac_system_role_immutable"
    ROLE_IN_USE = "rbac_role_in_use"
    CANNOT_REMOVE_LAST_OWNER = "rbac_cannot_remove_last_owner"
    TARGET_USER_NOT_FOUND = "rbac_target_user_not_found"
    PERMISSION_DENIED = "rbac_permission_denied"
    UNKNOWN_PERMISSION_ID = "rbac_unknown_permission_id"
```

- [ ] **Step 3: Write `models.py`**

```python
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

    role: Mapped["Role"] = relationship(lazy="joined")
```

- [ ] **Step 4: Verify it imports cleanly**

Run: `cd backend && python -c "from app.modules.rbac.models import Role, Permission, RolePermission, UserRole; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/rbac/__init__.py backend/app/modules/rbac/constants.py backend/app/modules/rbac/models.py
git commit -m "feat(rbac): constants and ORM models"
```

---

### Task 3: `rbac` exceptions + schemas

**Files:**
- Create: `backend/app/modules/rbac/exceptions.py`
- Create: `backend/app/modules/rbac/schemas.py`

**Interfaces:**
- Consumes: `ErrorCode` (Task 2), `RbacLimits` (Task 2).
- Produces: `PermissionRead`, `RoleRead`, `RoleCreate`, `RoleUpdate`, `RoleSummary`; exceptions `RoleNotFound`, `DuplicateRoleName`, `SystemRoleImmutable`, `RoleInUse`, `CannotRemoveLastOwner`, `TargetUserNotFound`, `PermissionDenied`, `UnknownPermissionId`.

- [ ] **Step 1: Write `exceptions.py`**

```python
"""Errors owned by the rbac module."""

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from app.modules.rbac.constants import ErrorCode


class RoleNotFound(NotFoundError):
    """Raised when no role matches the requested id."""

    code = ErrorCode.ROLE_NOT_FOUND
    message = "Role not found"


class DuplicateRoleName(ConflictError):
    """Raised when a role name is already taken."""

    code = ErrorCode.DUPLICATE_ROLE_NAME
    message = "A role with this name already exists"


class SystemRoleImmutable(ForbiddenError):
    """Raised when renaming or deleting one of the seeded owner/admin/member roles."""

    code = ErrorCode.SYSTEM_ROLE_IMMUTABLE
    message = "This role's name cannot be changed and it cannot be deleted"


class RoleInUse(ConflictError):
    """Raised when deleting a role that still has users assigned to it."""

    code = ErrorCode.ROLE_IN_USE
    message = "This role still has users assigned to it"


class CannotRemoveLastOwner(ValidationFailedError):
    """Raised when an action would leave zero users holding the owner role."""

    code = ErrorCode.CANNOT_REMOVE_LAST_OWNER
    message = "This is the last user with the owner role — assign it to someone else first"


class TargetUserNotFound(NotFoundError):
    """Raised when assigning a role to a user id that doesn't exist in auth."""

    code = ErrorCode.TARGET_USER_NOT_FOUND
    message = "User not found"


class PermissionDenied(ForbiddenError):
    """Raised by require_permission when the current user's role lacks resource.action."""

    code = ErrorCode.PERMISSION_DENIED
    message = "Missing permission"


class UnknownPermissionId(ValidationFailedError):
    """Raised when a role create/update references a permission id not in the catalog."""

    code = ErrorCode.UNKNOWN_PERMISSION_ID
    message = "Unknown permission id"
```

- [ ] **Step 2: Write `schemas.py`**

```python
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
```

- [ ] **Step 3: Verify it imports cleanly**

Run: `cd backend && python -c "from app.modules.rbac.schemas import RoleRead, RoleCreate, RoleUpdate, RoleSummary, RoleAssignment; from app.modules.rbac.exceptions import PermissionDenied; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/rbac/exceptions.py backend/app/modules/rbac/schemas.py
git commit -m "feat(rbac): exceptions and schemas"
```

---

### Task 4: `rbac` rules (pure, TDD)

**Files:**
- Create: `backend/app/modules/rbac/rules.py`
- Test: `backend/tests/rbac/__init__.py`
- Test: `backend/tests/rbac/test_rules.py`

**Interfaces:**
- Consumes: `RbacDefaults` (Task 2), `RoleRead` (Task 3).
- Produces: `RbacRules.can_delete_role(role) -> bool`, `RbacRules.can_rename_role(role) -> bool`, `RbacRules.blocks_last_owner_removal(role_name, remaining_owner_grants) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for app.modules.rbac.rules — pure decisions, no I/O, no fixtures."""

import pytest

from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import RoleRead


def _role(*, is_system: bool) -> RoleRead:
    return RoleRead(id=1, name="owner" if is_system else "custom", is_system=is_system, permissions=[])


@pytest.mark.parametrize(("is_system", "expected"), [(True, False), (False, True)])
def test_can_delete_role(is_system: bool, expected: bool) -> None:
    assert RbacRules.can_delete_role(_role(is_system=is_system)) is expected


@pytest.mark.parametrize(("is_system", "expected"), [(True, False), (False, True)])
def test_can_rename_role(is_system: bool, expected: bool) -> None:
    assert RbacRules.can_rename_role(_role(is_system=is_system)) is expected


@pytest.mark.parametrize(
    ("role_name", "remaining_owner_grants", "expected"),
    [
        ("owner", 1, True),  # this is the only owner left — block
        ("owner", 2, False),  # another owner still exists — fine
        ("admin", 1, False),  # not the owner role at all — never blocked
        ("member", 0, False),
    ],
)
def test_blocks_last_owner_removal(role_name: str, remaining_owner_grants: int, expected: bool) -> None:
    assert RbacRules.blocks_last_owner_removal(role_name, remaining_owner_grants) is expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/rbac/test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.rbac.rules'`

- [ ] **Step 3: Write the implementation**

```python
"""Business rules for the rbac module. Pure decisions: no I/O, no framework."""

from app.core.base.markers import rule
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.schemas import RoleRead


class RbacRules:
    """Every business decision about a role or a role grant."""

    @staticmethod
    @rule
    def can_delete_role(role: RoleRead) -> bool:
        """A system-seeded role (owner/admin/member) can never be deleted."""
        return not role.is_system

    @staticmethod
    @rule
    def can_rename_role(role: RoleRead) -> bool:
        """A system-seeded role's name is fixed; its permission set is still editable."""
        return not role.is_system

    @staticmethod
    @rule
    def blocks_last_owner_removal(role_name: str, remaining_owner_grants: int) -> bool:
        """True when reassigning/blocking this grant would leave zero users able to
        manage roles or users. remaining_owner_grants counts owner-role holders
        *including* the one about to be changed."""
        return role_name == RbacDefaults.OWNER_ROLE_NAME and remaining_owner_grants <= 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/rbac/test_rules.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/rbac/rules.py backend/tests/rbac/__init__.py backend/tests/rbac/test_rules.py
git commit -m "feat(rbac): pure business rules for role mutation and bus-factor safety"
```

---

### Task 5: `rbac` repository

**Files:**
- Create: `backend/app/modules/rbac/repository.py`

**Interfaces:**
- Consumes: `Role`/`Permission`/`RolePermission`/`UserRole` models (Task 2), `RoleRead`/`PermissionRead` schemas (Task 3).
- Produces: `AbstractRoleRepository`/`RoleRepository`, `AbstractPermissionRepository`/`PermissionRepository`, `AbstractUserRoleRepository`/`UserRoleRepository` — exact method signatures below, consumed by Task 6 (uow) and Task 7 (services).

No dedicated repository test file — covered through Task 9's/Task 12's router integration tests, matching this project's existing convention (`auth/repository.py` has no `test_repository.py` either; it's exercised via `test_router.py`).

- [ ] **Step 1: Write `repository.py`**

```python
"""Single access path to the rbac tables (roles, permissions, role_permissions, user_roles)."""

from abc import ABC, abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.rbac.schemas import PermissionRead, RoleRead


def _to_role_read(row: Role) -> RoleRead:
    return RoleRead(
        id=row.id,
        name=row.name,
        is_system=row.is_system,
        permissions=[PermissionRead.model_validate(p) for p in row.permissions],
    )


class AbstractRoleRepository(AbstractRepository[RoleRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def find_by_name(self, name: str) -> RoleRead | None:
        """Look up a role by its unique name."""
        raise NotImplementedError

    @abstractmethod
    async def create(self, *, name: str, is_system: bool, permission_ids: list[int]) -> RoleRead:
        """Create a role with an initial permission set."""
        raise NotImplementedError

    @abstractmethod
    async def update(self, role_id: int, *, name: str | None, permission_ids: list[int] | None) -> RoleRead:
        """Rename and/or replace a role's permission set. None means unchanged."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, role_id: int) -> None:
        """Delete a role. Caller is responsible for the is_system/in-use checks."""
        raise NotImplementedError

    @abstractmethod
    async def count_users_with_role(self, role_id: int) -> int:
        """Count how many users currently hold this role."""
        raise NotImplementedError


class RoleRepository(AbstractRoleRepository):
    """SQLAlchemy implementation. Every read/write of roles+role_permissions goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get(self, role_id: int) -> Role | None:
        return await self._session.scalar(
            select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
        )

    @database
    async def get_by_id(self, entity_id: int) -> RoleRead | None:
        """Return one role with its permissions, or None when it does not exist."""
        row = await self._get(entity_id)
        return _to_role_read(row) if row else None

    @database
    async def find_by_name(self, name: str) -> RoleRead | None:
        """Look up a role by its unique name."""
        row = await self._session.scalar(
            select(Role).options(selectinload(Role.permissions)).where(Role.name == name)
        )
        return _to_role_read(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[RoleRead], int]:
        """Return one page of roles, each with its permissions, plus the total count."""
        rows = await self._session.scalars(
            select(Role)
            .options(selectinload(Role.permissions))
            .order_by(Role.id)
            .limit(limit)
            .offset(offset)
        )
        items = [_to_role_read(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Role))
        return items, total or 0

    @database
    async def create(self, *, name: str, is_system: bool, permission_ids: list[int]) -> RoleRead:
        """Create a role with an initial permission set."""
        row = Role(name=name, is_system=is_system)
        self._session.add(row)
        await self._session.flush()
        for permission_id in permission_ids:
            self._session.add(RolePermission(role_id=row.id, permission_id=permission_id))
        await self._session.flush()
        return await self.get_by_id(row.id)  # type: ignore[return-value]

    @database
    async def update(self, role_id: int, *, name: str | None, permission_ids: list[int] | None) -> RoleRead:
        """Rename and/or replace a role's permission set. None means unchanged."""
        row = await self._session.get(Role, role_id)
        if row is None:
            raise ValueError(f"role {role_id} does not exist")
        if name is not None:
            row.name = name
        if permission_ids is not None:
            await self._session.execute(
                RolePermission.__table__.delete().where(RolePermission.role_id == role_id)
            )
            for permission_id in permission_ids:
                self._session.add(RolePermission(role_id=role_id, permission_id=permission_id))
        await self._session.flush()
        return await self.get_by_id(role_id)  # type: ignore[return-value]

    @database
    async def delete(self, role_id: int) -> None:
        """Delete a role. Caller is responsible for the is_system/in-use checks."""
        row = await self._session.get(Role, role_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def count_users_with_role(self, role_id: int) -> int:
        """Count how many users currently hold this role."""
        total = await self._session.scalar(
            select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)
        )
        return total or 0


class AbstractPermissionRepository(AbstractRepository[PermissionRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_all(self) -> list[PermissionRead]:
        """Return the full permission catalog, unpaginated (it's small and fixed)."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_ids(self, ids: list[int]) -> list[PermissionRead]:
        """Return the permissions matching the given ids (fewer than requested if some don't exist)."""
        raise NotImplementedError


class PermissionRepository(AbstractPermissionRepository):
    """SQLAlchemy implementation. Read-only — the catalog is written only by the seed script."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: int) -> PermissionRead | None:
        """Return one permission, or None when it does not exist."""
        row = await self._session.get(Permission, entity_id)
        return PermissionRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[PermissionRead], int]:
        """Return one page of the permission catalog together with the total count."""
        rows = await self._session.scalars(
            select(Permission).order_by(Permission.id).limit(limit).offset(offset)
        )
        items = [PermissionRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(Permission))
        return items, total or 0

    @database
    async def list_all(self) -> list[PermissionRead]:
        """Return the full permission catalog, unpaginated (it's small and fixed)."""
        rows = await self._session.scalars(select(Permission).order_by(Permission.resource, Permission.action))
        return [PermissionRead.model_validate(row) for row in rows]

    @database
    async def find_by_ids(self, ids: list[int]) -> list[PermissionRead]:
        """Return the permissions matching the given ids (fewer than requested if some don't exist)."""
        if not ids:
            return []
        rows = await self._session.scalars(select(Permission).where(Permission.id.in_(ids)))
        return [PermissionRead.model_validate(row) for row in rows]


class AbstractUserRoleRepository(ABC):
    """Contract for the single-role-per-user grant. Not an AbstractRepository[T]: this
    store is one row per user with no listing use case, the same shape as
    app.integrations.dx_core.repository.AbstractDxTokenRepository — see that file's
    docstring for why forcing get_by_id/list_page here would add nothing."""

    @abstractmethod
    async def get_role_for_user(self, user_id: int) -> RoleRead | None:
        """Return the role currently granted to a user, or None if never assigned."""
        raise NotImplementedError

    @abstractmethod
    async def assign(self, user_id: int, role_id: int) -> None:
        """Upsert a user's single role grant."""
        raise NotImplementedError

    @abstractmethod
    async def user_has_permission(self, user_id: int, resource: str, action: str) -> bool:
        """Return whether user_id's granted role includes resource.action."""
        raise NotImplementedError


class UserRoleRepository(AbstractUserRoleRepository):
    """SQLAlchemy implementation. Every read/write of user_roles goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_role_for_user(self, user_id: int) -> RoleRead | None:
        """Return the role currently granted to a user, or None if never assigned."""
        row = await self._session.scalar(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .options(selectinload(Role.permissions))
            .where(UserRole.user_id == user_id)
        )
        return _to_role_read(row) if row else None

    @database
    async def assign(self, user_id: int, role_id: int) -> None:
        """Upsert a user's single role grant."""
        row = await self._session.get(UserRole, user_id)
        if row is None:
            self._session.add(UserRole(user_id=user_id, role_id=role_id))
        else:
            row.role_id = role_id
        await self._session.flush()

    @database
    async def user_has_permission(self, user_id: int, resource: str, action: str) -> bool:
        """Return whether user_id's granted role includes resource.action."""
        stmt = (
            select(Permission.id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Permission.resource == resource, Permission.action == action)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None
```

Note: `Role.permissions` is referenced via `selectinload(Role.permissions)` but Task 2's `Role` model has no `permissions` relationship defined yet — add it now:

- [ ] **Step 2: Add the missing relationship to `models.py`**

In `backend/app/modules/rbac/models.py`, add to `Role`:

```python
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", lazy="noload", viewonly=True
    )
```
(`viewonly=True` because writes to the matrix always go through `RolePermission` rows explicitly in `RoleRepository.create`/`update`, never through this relationship's own session-tracked collection — same reasoning as `User.department`'s `lazy="joined"` being read-only in the existing auth module.)

- [ ] **Step 3: Verify it imports cleanly**

Run: `cd backend && python -c "from app.modules.rbac.repository import RoleRepository, PermissionRepository, UserRoleRepository; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/rbac/repository.py backend/app/modules/rbac/models.py
git commit -m "feat(rbac): repository layer for roles, permissions, and user role grants"
```

---

### Task 6: `rbac` unit of work

**Files:**
- Create: `backend/app/modules/rbac/uow.py`

**Interfaces:**
- Consumes: repositories from Task 5.
- Produces: `AbstractRbacUnitOfWork` (fields `roles`, `permissions`, `user_roles`), `RbacUnitOfWork`.

- [ ] **Step 1: Write `uow.py`**

```python
"""Transaction boundary for the rbac module."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.modules.rbac.repository import (
    AbstractPermissionRepository,
    AbstractRoleRepository,
    AbstractUserRoleRepository,
    PermissionRepository,
    RoleRepository,
    UserRoleRepository,
)

logger = logging.getLogger(__name__)


class AbstractRbacUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    roles: AbstractRoleRepository
    permissions: AbstractPermissionRepository
    user_roles: AbstractUserRoleRepository


class RbacUnitOfWork(AbstractRbacUnitOfWork):
    """Owns the transaction for the rbac module's tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.roles = RoleRepository(session)
        self.permissions = PermissionRepository(session)
        self.user_roles = UserRoleRepository(session)

    @database
    async def commit(self) -> None:
        """Commit the transaction."""
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        logger.warning("rbac unit of work rolled back")
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `cd backend && python -c "from app.modules.rbac.uow import RbacUnitOfWork; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/modules/rbac/uow.py
git commit -m "feat(rbac): unit of work"
```

---

### Task 7: `rbac` services (TDD via Fakes)

**Files:**
- Create: `backend/app/modules/rbac/services/__init__.py`
- Create: `backend/app/modules/rbac/services/create_role.py`
- Create: `backend/app/modules/rbac/services/update_role.py`
- Create: `backend/app/modules/rbac/services/delete_role.py`
- Create: `backend/app/modules/rbac/services/assign_role.py`
- Create: `backend/app/modules/rbac/services/assign_default_role.py`
- Test: `backend/tests/rbac/test_services.py`

**Interfaces:**
- Consumes: `AbstractRbacUnitOfWork` (Task 6), `RbacRules` (Task 4), exceptions (Task 3).
- Produces: `CreateRole(uow).execute(name, permission_ids) -> RoleRead`, `UpdateRole(uow).execute(role_id, name, permission_ids) -> RoleRead`, `DeleteRole(uow).execute(role_id) -> None`, `AssignRole(uow, user_lookup).execute(user_id, role_id) -> None` where `user_lookup: Callable[[int], Awaitable[UserRead | None]]`, `AssignDefaultRole(uow).execute(user_id) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the rbac module's use cases. No database — every collaborator
is a fake implementing the module's own Abstract* contract."""

import pytest

from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.exceptions import (
    CannotRemoveLastOwner,
    DuplicateRoleName,
    RoleInUse,
    RoleNotFound,
    SystemRoleImmutable,
    TargetUserNotFound,
    UnknownPermissionId,
)
from app.modules.rbac.repository import (
    AbstractPermissionRepository,
    AbstractRoleRepository,
    AbstractUserRoleRepository,
)
from app.modules.rbac.schemas import PermissionRead, RoleRead
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork

_CATALOG = [
    PermissionRead(id=1, resource="role", action="read", description="View roles"),
    PermissionRead(id=2, resource="role", action="create", description="Create roles"),
]


class FakeRoleRepository(AbstractRoleRepository):
    def __init__(self) -> None:
        self._rows: dict[int, RoleRead] = {}
        self._next_id = 1
        self._grants: dict[int, int] = {}  # role_id -> count, set by tests via seed_grants

    async def get_by_id(self, entity_id: int) -> RoleRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[RoleRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def find_by_name(self, name: str) -> RoleRead | None:
        return next((r for r in self._rows.values() if r.name == name), None)

    async def create(self, *, name: str, is_system: bool, permission_ids: list[int]) -> RoleRead:
        permissions = [p for p in _CATALOG if p.id in permission_ids]
        role = RoleRead(id=self._next_id, name=name, is_system=is_system, permissions=permissions)
        self._rows[role.id] = role
        self._next_id += 1
        return role

    async def update(self, role_id: int, *, name: str | None, permission_ids: list[int] | None) -> RoleRead:
        existing = self._rows[role_id]
        permissions = existing.permissions
        if permission_ids is not None:
            permissions = [p for p in _CATALOG if p.id in permission_ids]
        updated = existing.model_copy(update={"name": name or existing.name, "permissions": permissions})
        self._rows[role_id] = updated
        return updated

    async def delete(self, role_id: int) -> None:
        self._rows.pop(role_id, None)

    async def count_users_with_role(self, role_id: int) -> int:
        return self._grants.get(role_id, 0)

    def seed(self, role: RoleRead, *, grants: int = 0) -> None:
        self._rows[role.id] = role
        self._next_id = max(self._next_id, role.id + 1)
        self._grants[role.id] = grants


class FakePermissionRepository(AbstractPermissionRepository):
    async def get_by_id(self, entity_id: int) -> PermissionRead | None:
        return next((p for p in _CATALOG if p.id == entity_id), None)

    async def list_page(self, limit: int, offset: int) -> tuple[list[PermissionRead], int]:
        return _CATALOG[offset : offset + limit], len(_CATALOG)

    async def list_all(self) -> list[PermissionRead]:
        return list(_CATALOG)

    async def find_by_ids(self, ids: list[int]) -> list[PermissionRead]:
        return [p for p in _CATALOG if p.id in ids]


class FakeUserRoleRepository(AbstractUserRoleRepository):
    def __init__(self) -> None:
        self.grants: dict[int, int] = {}  # user_id -> role_id

    async def get_role_for_user(self, user_id: int) -> RoleRead | None:
        return None  # not exercised by the services under test here

    async def assign(self, user_id: int, role_id: int) -> None:
        self.grants[user_id] = role_id

    async def user_has_permission(self, user_id: int, resource: str, action: str) -> bool:
        return False  # not exercised by the services under test here


class FakeRbacUnitOfWork(AbstractRbacUnitOfWork):
    def __init__(self) -> None:
        self.roles = FakeRoleRepository()
        self.permissions = FakePermissionRepository()
        self.user_roles = FakeUserRoleRepository()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def _owner_role(*, grants: int) -> RoleRead:
    return RoleRead(id=10, name=RbacDefaults.OWNER_ROLE_NAME, is_system=True, permissions=[])


class TestCreateRole:
    async def test_creates_role_with_given_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()

        role = await CreateRole(uow).execute("support", [1, 2])

        assert role.name == "support"
        assert role.is_system is False
        assert {p.id for p in role.permissions} == {1, 2}
        assert uow.commits == 1

    async def test_rejects_duplicate_name(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        with pytest.raises(DuplicateRoleName):
            await CreateRole(uow).execute("support", [])

    async def test_rejects_unknown_permission_id(self) -> None:
        uow = FakeRbacUnitOfWork()

        with pytest.raises(UnknownPermissionId):
            await CreateRole(uow).execute("support", [999])


class TestUpdateRole:
    async def test_renames_a_custom_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        updated = await UpdateRole(uow).execute(1, name="support-l1", permission_ids=None)

        assert updated.name == "support-l1"

    async def test_rejects_renaming_a_system_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_owner_role(grants=1))

        with pytest.raises(SystemRoleImmutable):
            await UpdateRole(uow).execute(10, name="root", permission_ids=None)

    async def test_allows_editing_a_system_roles_permissions(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_owner_role(grants=1))

        updated = await UpdateRole(uow).execute(10, name=None, permission_ids=[1])

        assert {p.id for p in updated.permissions} == {1}

    async def test_missing_role_raises(self) -> None:
        uow = FakeRbacUnitOfWork()

        with pytest.raises(RoleNotFound):
            await UpdateRole(uow).execute(404, name="x", permission_ids=None)


class TestDeleteRole:
    async def test_deletes_a_custom_role_with_no_users(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]), grants=0)

        await DeleteRole(uow).execute(1)

        assert await uow.roles.get_by_id(1) is None

    async def test_rejects_deleting_a_system_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_owner_role(grants=1))

        with pytest.raises(SystemRoleImmutable):
            await DeleteRole(uow).execute(10)

    async def test_rejects_deleting_a_role_still_in_use(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]), grants=2)

        with pytest.raises(RoleInUse):
            await DeleteRole(uow).execute(1)


class TestAssignRole:
    async def test_assigns_role_to_an_existing_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return object()  # any non-None sentinel — AssignRole only checks for None

        await AssignRole(uow, user_lookup).execute(42, 1)

        assert uow.user_roles.grants[42] == 1

    async def test_rejects_unknown_user(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return None

        with pytest.raises(TargetUserNotFound):
            await AssignRole(uow, user_lookup).execute(42, 1)

    async def test_rejects_reassigning_the_last_owner_away(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(_owner_role(grants=1))
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))
        uow.user_roles.grants[42] = 10  # currently the owner

        async def user_lookup(user_id: int):
            return object()

        with pytest.raises(CannotRemoveLastOwner):
            await AssignRole(uow, user_lookup).execute(42, 1)

    async def test_missing_target_role_raises(self) -> None:
        uow = FakeRbacUnitOfWork()

        async def user_lookup(user_id: int):
            return object()

        with pytest.raises(RoleNotFound):
            await AssignRole(uow, user_lookup).execute(42, 404)


class TestAssignDefaultRole:
    async def test_grants_the_seeded_member_role(self) -> None:
        uow = FakeRbacUnitOfWork()
        member = RoleRead(id=3, name=RbacDefaults.MEMBER_ROLE_NAME, is_system=True, permissions=[])
        uow.roles.seed(member)

        await AssignDefaultRole(uow).execute(99)

        assert uow.user_roles.grants[99] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/rbac/test_services.py -v`
Expected: FAIL — `ModuleNotFoundError` for each `services.*` module.

- [ ] **Step 3: Write the implementations**

```python
# backend/app/modules/rbac/services/__init__.py
"""Use cases owned by the rbac module. One file, one class, per app/use_case.py rule #9."""
```

```python
# backend/app/modules/rbac/services/create_role.py
"""Use case: create a new custom role with an initial permission set."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.exceptions import DuplicateRoleName, UnknownPermissionId
from app.modules.rbac.schemas import RoleRead
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class CreateRole(AbstractUseCase):
    """Create a role. Always is_system=False — only the seed script creates system roles."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, name: str, permission_ids: list[int]) -> RoleRead:
        if await self._uow.roles.find_by_name(name) is not None:
            raise DuplicateRoleName()
        found = await self._uow.permissions.find_by_ids(permission_ids)
        if len(found) != len(set(permission_ids)):
            raise UnknownPermissionId()
        role = await self._uow.roles.create(name=name, is_system=False, permission_ids=permission_ids)
        await self._uow.commit()
        return role
```

```python
# backend/app/modules/rbac/services/update_role.py
"""Use case: rename a role and/or replace its permission set."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.exceptions import RoleNotFound, SystemRoleImmutable, UnknownPermissionId
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import RoleRead
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class UpdateRole(AbstractUseCase):
    """A system role's permissions stay editable even though its name is locked
    (RbacRules.can_rename_role) — see spec's role.update note."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, role_id: int, *, name: str | None, permission_ids: list[int] | None) -> RoleRead:
        role = await self._uow.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound()
        if name is not None and not RbacRules.can_rename_role(role):
            raise SystemRoleImmutable()
        if permission_ids is not None:
            found = await self._uow.permissions.find_by_ids(permission_ids)
            if len(found) != len(set(permission_ids)):
                raise UnknownPermissionId()
        updated = await self._uow.roles.update(role_id, name=name, permission_ids=permission_ids)
        await self._uow.commit()
        return updated
```

```python
# backend/app/modules/rbac/services/delete_role.py
"""Use case: delete a custom role."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.exceptions import RoleInUse, RoleNotFound, SystemRoleImmutable
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class DeleteRole(AbstractUseCase):
    """Blocked for a system role (RbacRules.can_delete_role) and for a role still
    granted to at least one user — reassign them first."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, role_id: int) -> None:
        role = await self._uow.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound()
        if not RbacRules.can_delete_role(role):
            raise SystemRoleImmutable()
        if await self._uow.roles.count_users_with_role(role_id) > 0:
            raise RoleInUse()
        await self._uow.roles.delete(role_id)
        await self._uow.commit()
```

```python
# backend/app/modules/rbac/services/assign_role.py
"""Use case: assign a role to an existing user (admin action)."""

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.exceptions import CannotRemoveLastOwner, RoleNotFound, TargetUserNotFound
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.uow import AbstractRbacUnitOfWork

UserLookup = Callable[[int], Awaitable[Any | None]]


class AssignRole(AbstractUseCase):
    """user_lookup is injected rather than importing auth directly, so this
    service depends only on a narrow capability — dependencies.py wires it to
    app.modules.auth.public.AuthApi.get_user_by_id (the one facade call to the
    module that actually owns the users table)."""

    def __init__(self, uow: AbstractRbacUnitOfWork, user_lookup: UserLookup) -> None:
        self._uow = uow
        self._user_lookup = user_lookup

    @use_case
    async def execute(self, user_id: int, role_id: int) -> None:
        if await self._user_lookup(user_id) is None:
            raise TargetUserNotFound()
        role = await self._uow.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound()

        current = await self._uow.user_roles.get_role_for_user(user_id)
        if current is not None:
            owner_grants = await self._uow.roles.count_users_with_role(current.id)
            if RbacRules.blocks_last_owner_removal(current.name, owner_grants):
                raise CannotRemoveLastOwner()

        await self._uow.user_roles.assign(user_id, role_id)
        await self._uow.commit()
```

```python
# backend/app/modules/rbac/services/assign_default_role.py
"""Use case: grant the seeded default role to a newly synced user."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class AssignDefaultRole(AbstractUseCase):
    """Called by auth's AuthenticateWithDx right after a brand new user is created —
    replaces the old DX-role-code auto-mapping (RoleMapping/resolve_role, removed)."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, user_id: int) -> None:
        role = await self._uow.roles.find_by_name(RbacDefaults.DEFAULT_ROLE_NAME)
        if role is None:
            raise RuntimeError(
                f"seed role {RbacDefaults.DEFAULT_ROLE_NAME!r} missing — run `python -m app.seeds.seed_rbac`"
            )
        await self._uow.user_roles.assign(user_id, role.id)
        # deliberately no commit() here — see Task 11: this runs inside
        # AuthenticateWithDx's transaction and is committed by auth's own uow.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/rbac/test_services.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/rbac/services backend/tests/rbac/test_services.py
git commit -m "feat(rbac): role CRUD, role assignment, and default-role use cases"
```

---

### Task 8: `auth` facade extension + `rbac` dependencies + `rbac` public facade

**Files:**
- Modify: `backend/app/modules/auth/public.py`
- Modify: `backend/app/modules/auth/dependencies.py`
- Create: `backend/app/modules/rbac/dependencies.py`
- Create: `backend/app/modules/rbac/public.py`

**Interfaces:**
- Consumes: services (Task 7), `AbstractRbacUnitOfWork` (Task 6).
- Produces: `auth.public.AuthApi.get_user_by_id(user_id) -> UserRead | None`; `rbac.public.require_permission(resource, action)` (FastAPI dependency factory), `RbacApi.assign_default_role(user_id)`, `RbacApi.role_summary_for_user(user_id) -> RoleSummary`, `RbacApi.is_last_owner(user_id) -> bool`, `get_rbac_api`.

No new tests in this task — these are composition-root wiring functions, exercised end to end by Task 9's/Task 12's router tests (matching how `auth/dependencies.py`/`auth/public.py` have no dedicated test file today either).

- [ ] **Step 1: Extend `auth/public.py`**

```python
"""Contract exposed to other modules.

Other modules import this file and nothing else from auth. Reaching into
repository.py or models.py couples them to storage details and makes this
module impossible to extract later.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.auth.dependencies import get_current_user, get_uow
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork


class AuthApi:
    """Facade over the signed in user, plus a narrow by-id lookup for other
    modules' cross-module existence checks (e.g. rbac validating a role
    assignment's target user)."""

    def __init__(self, user: UserRead, uow: AbstractAuthUnitOfWork) -> None:
        self._user = user
        self._uow = uow

    @facade
    def current_user(self) -> UserRead:
        """Return the signed in user resolved for this request."""
        return self._user

    @facade
    async def get_user_by_id(self, user_id: int) -> UserRead | None:
        """Look up any user by id. For a single existence check from another
        module — never for bulk reads, which would mean that module wants its
        own list_page-shaped facade method instead."""
        return await self._uow.users.get_by_id(user_id)


async def get_auth_api(
    user: UserRead = Depends(get_current_user),
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
) -> AuthApi:
    """Provide the facade to other modules."""
    return AuthApi(user, uow)
```

- [ ] **Step 2: Confirm `auth/dependencies.py` needs no change**

`get_uow`/`get_current_user` already exist and are exactly what Step 1 imports — this step is a read-only check, not an edit.

Run: `cd backend && grep -n "^async def get_uow\|^async def get_current_user" app/modules/auth/dependencies.py`
Expected: both lines found, signatures matching what Step 1's imports expect.

- [ ] **Step 3: Write `rbac/dependencies.py`**

```python
"""Dependency wiring for the rbac module.

The composition root: the only place that names a concrete class
(RbacUnitOfWork) instead of its Abstract* contract.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork, RbacUnitOfWork


async def get_uow(session: AsyncSession = Depends(get_session)) -> RbacUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return RbacUnitOfWork(session)


async def get_create_role(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> CreateRole:
    """Provide the create-role use case."""
    return CreateRole(uow)


async def get_update_role(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> UpdateRole:
    """Provide the update-role use case."""
    return UpdateRole(uow)


async def get_delete_role(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> DeleteRole:
    """Provide the delete-role use case."""
    return DeleteRole(uow)


async def get_assign_default_role(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> AssignDefaultRole:
    """Provide the default-role-grant use case, used by auth's SSO sync flow."""
    return AssignDefaultRole(uow)
```

`get_assign_role` (needs `AuthApi.get_user_by_id`) is wired in Step 4 below, in `public.py`, since it composes across the module boundary the same way `auth/public.py`'s `get_auth_api` does — keeping that composition in `dependencies.py` would make `dependencies.py` reach across modules, which is `public.py`'s job.

- [ ] **Step 4: Write `rbac/public.py`**

```python
"""Contract exposed to other modules — and the require_permission dependency
every other module's router gates its endpoints with. This is the ONLY file
another module may import from rbac.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.auth.schemas import UserRead
from app.modules.rbac.exceptions import PermissionDenied
from app.modules.rbac.schemas import RoleSummary
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork
from app.modules.rbac.dependencies import get_uow


class RbacApi:
    """Facade over role/permission lookups other modules need."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @facade
    async def assign_default_role(self, user_id: int) -> None:
        """Grant the seeded default role. See services/assign_default_role.py."""
        from app.modules.rbac.services.assign_default_role import AssignDefaultRole

        await AssignDefaultRole(self._uow).execute(user_id)

    @facade
    async def role_summary_for_user(self, user_id: int) -> RoleSummary:
        """Return role name + flat 'resource.action' permission strings, for
        auth/me to compose into the session the frontend's PermissionProvider seeds from."""
        role = await self._uow.user_roles.get_role_for_user(user_id)
        if role is None:
            return RoleSummary(role_name="", permissions=[])
        return RoleSummary(
            role_name=role.name, permissions=[f"{p.resource}.{p.action}" for p in role.permissions]
        )

    @facade
    async def is_last_owner(self, user_id: int) -> bool:
        """True if user_id holds the owner role and is the only one who does —
        used by auth's UpdateUserStatus to block blocking the last owner."""
        from app.modules.rbac.constants import RbacDefaults
        from app.modules.rbac.rules import RbacRules

        role = await self._uow.user_roles.get_role_for_user(user_id)
        if role is None or role.name != RbacDefaults.OWNER_ROLE_NAME:
            return False
        owner_grants = await self._uow.roles.count_users_with_role(role.id)
        return RbacRules.blocks_last_owner_removal(role.name, owner_grants)


async def get_rbac_api(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> RbacApi:
    """Provide the facade to other modules."""
    return RbacApi(uow)


async def get_assign_role(
    uow: AbstractRbacUnitOfWork = Depends(get_uow),
    auth_api: AuthApi = Depends(get_auth_api),
) -> AssignRole:
    """Provide the assign-role use case, wired to auth's user-existence check."""
    return AssignRole(uow, auth_api.get_user_by_id)


def require_permission(resource: str, action: str):
    """Return a dependency that 403s unless the current user's role grants
    resource.action. Routes ask 'can this user do X,' never 'does this user
    have role Y' — see references/rbac.md."""

    async def check(
        auth_api: AuthApi = Depends(get_auth_api),
        uow: AbstractRbacUnitOfWork = Depends(get_uow),
    ) -> UserRead:
        user = auth_api.current_user()
        if not await uow.user_roles.user_has_permission(user.id, resource, action):
            raise PermissionDenied(resource=resource, action=action)
        return user

    return check
```

Note: the two local imports inside `assign_default_role`/`is_last_owner` (Step 4) avoid a real circular import — `rbac/services/assign_default_role.py` and `rbac/rules.py` both import from `rbac/uow.py`, which `public.py` also imports; a top-level import here would work today but the local-import guard keeps this file resilient if `services/`'s own imports grow. Per rule #13, a local import is only acceptable to break an *actual* cycle — verify at Step 6 that removing them and importing at the top does **not** in fact raise `ImportError` (it should import fine, since `services/assign_default_role.py` doesn't import `public.py`); if it imports cleanly at the top, move both imports to the top of the file instead of leaving them local, since rule #13 treats an unnecessary local import as a lint finding, not a style choice.

- [ ] **Step 5: Verify it imports cleanly**

Run: `cd backend && python -c "from app.modules.rbac.public import require_permission, get_rbac_api, RbacApi; from app.modules.auth.public import AuthApi, get_auth_api; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Move the two local imports to the top of `public.py`, per the note in Step 4**

Edit `rbac/public.py`: add `from app.modules.rbac.constants import RbacDefaults`, `from app.modules.rbac.rules import RbacRules`, `from app.modules.rbac.services.assign_default_role import AssignDefaultRole` to the top-level import block; delete the two local `from ... import ...` lines inside the methods.

Run: `python -c "from app.modules.rbac.public import RbacApi; print('ok')"`
Expected: `ok` (confirms no circular import — if this fails, revert to the local-import form and note the real cycle instead)

- [ ] **Step 7: `ruff check`**

Run: `ruff check app/modules/auth/public.py app/modules/rbac/dependencies.py app/modules/rbac/public.py`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/auth/public.py backend/app/modules/rbac/dependencies.py backend/app/modules/rbac/public.py
git commit -m "feat(rbac): require_permission dependency and cross-module facades"
```

---

### Task 9: `rbac` router + app wiring + seed script

**Files:**
- Create: `backend/app/modules/rbac/router.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/seeds/seed_rbac.py`
- Test: `backend/tests/rbac/test_router.py`

**Interfaces:**
- Consumes: everything from Tasks 2–8.
- Produces: `GET/POST /api/v1/rbac/roles`, `GET/PATCH/DELETE /api/v1/rbac/roles/{id}`, `GET /api/v1/rbac/permissions`, `PATCH /api/v1/rbac/users/{user_id}/role`.

- [ ] **Step 1: Write `router.py`**

```python
"""HTTP entry points of the rbac module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result in
ApiResponse — no formatting/business logic lives here."""

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.auth.schemas import UserRead
from app.modules.rbac.public import get_assign_role, require_permission
from app.modules.rbac.schemas import PermissionRead, RoleAssignment, RoleCreate, RoleRead, RoleUpdate
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.services.create_role import CreateRole
from app.modules.rbac.services.delete_role import DeleteRole
from app.modules.rbac.services.update_role import UpdateRole
from app.modules.rbac.dependencies import get_create_role, get_delete_role, get_update_role
from app.modules.rbac.uow import AbstractRbacUnitOfWork
from app.modules.rbac.dependencies import get_uow as get_rbac_uow

router = APIRouter(prefix="/rbac", tags=["rbac"])


@router.post("/roles")
async def create_role(
    body: RoleCreate,
    use_case: CreateRole = Depends(get_create_role),
    _user: UserRead = Depends(require_permission("role", "create")),
) -> ApiResponse[RoleRead]:
    """Create a new custom role."""
    role = await use_case.execute(body.name, body.permission_ids)
    return ApiResponse[RoleRead](success=True, data=role)


@router.get("/roles")
async def list_roles(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission("role", "read")),
) -> ApiResponse[Page[RoleRead]]:
    """List roles with their permissions."""
    items, total = await uow.roles.list_page(pagination.limit, pagination.offset)
    page = Page[RoleRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[RoleRead]](success=True, data=page)


@router.get("/roles/{role_id}")
async def get_role(
    role_id: int,
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission("role", "read")),
) -> ApiResponse[RoleRead]:
    """Return one role, 404 if it doesn't exist."""
    from app.modules.rbac.exceptions import RoleNotFound

    role = await uow.roles.get_by_id(role_id)
    if role is None:
        raise RoleNotFound()
    return ApiResponse[RoleRead](success=True, data=role)


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: int,
    body: RoleUpdate,
    use_case: UpdateRole = Depends(get_update_role),
    _user: UserRead = Depends(require_permission("role", "update")),
) -> ApiResponse[RoleRead]:
    """Rename a role and/or replace its permission set."""
    role = await use_case.execute(role_id, name=body.name, permission_ids=body.permission_ids)
    return ApiResponse[RoleRead](success=True, data=role)


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    use_case: DeleteRole = Depends(get_delete_role),
    _user: UserRead = Depends(require_permission("role", "delete")),
) -> ApiResponse[None]:
    """Delete a custom role."""
    await use_case.execute(role_id)
    return ApiResponse[None](success=True)


@router.get("/permissions")
async def list_permissions(
    uow: AbstractRbacUnitOfWork = Depends(get_rbac_uow),
    _user: UserRead = Depends(require_permission("permission", "read")),
) -> ApiResponse[list[PermissionRead]]:
    """Return the fixed permission catalog, for building the role-edit checkbox UI."""
    permissions = await uow.permissions.list_all()
    return ApiResponse[list[PermissionRead]](success=True, data=permissions)


@router.patch("/users/{user_id}/role")
async def assign_user_role(
    user_id: int,
    body: RoleAssignment,
    use_case: AssignRole = Depends(get_assign_role),
    _user: UserRead = Depends(require_permission("user", "assign_role")),
) -> ApiResponse[None]:
    """Assign a role to an existing user."""
    await use_case.execute(user_id, body.role_id)
    return ApiResponse[None](success=True)
```

Fix the two function-body imports flagged by `ruff`'s `PLC0415` (added above only to keep the earlier explanation self-contained) — move both to the top of the file in the same step, since neither is breaking a real cycle:

```python
from app.modules.rbac.exceptions import RoleNotFound
```
goes into the top import block; delete the `get_role` function's local import line.

- [ ] **Step 2: Wire the router into `main.py`**

In `backend/app/main.py`, add the import and registration:

```python
from app.modules.rbac.router import router as rbac_router
```
(next to the existing `from app.modules.auth.router import router as auth_router`)

```python
app.include_router(rbac_router, prefix="/api/v1")
```
(next to the existing `app.include_router(auth_router, prefix="/api/v1")`)

- [ ] **Step 3: Write the seed script**

```python
"""Idempotent seed: the permission catalog and the three default roles.

Run via `python -m app.seeds.seed_rbac`. Safe to run on every deploy — new
permissions added to RbacPermissionCatalog.CATALOG appear on the next run
without touching existing role/permission rows.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.modules.rbac.constants import RbacDefaults, RbacPermissionCatalog
from app.modules.rbac.models import Permission, Role, RolePermission

logger = logging.getLogger(__name__)


async def run() -> None:
    """Upsert the permission catalog, then the three default roles."""
    engine = create_async_engine(str(settings.DATABASE_URL))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        permission_ids: list[int] = []
        for resource, action, description in RbacPermissionCatalog.CATALOG:
            row = await session.scalar(
                select(Permission).where(Permission.resource == resource, Permission.action == action)
            )
            if row is None:
                row = Permission(resource=resource, action=action, description=description)
                session.add(row)
                await session.flush()
            permission_ids.append(row.id)
        await session.commit()

        all_permission_ids = permission_ids
        for name, grants_everything in (
            (RbacDefaults.OWNER_ROLE_NAME, True),
            (RbacDefaults.ADMIN_ROLE_NAME, True),
            (RbacDefaults.MEMBER_ROLE_NAME, False),
        ):
            role = await session.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, is_system=True)
                session.add(role)
                await session.flush()
                if grants_everything:
                    for permission_id in all_permission_ids:
                        session.add(RolePermission(role_id=role.id, permission_id=permission_id))
                await session.flush()
                logger.info("seeded role %s", name)
        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 4: Write the router integration tests**

```python
"""Integration tests for app.modules.rbac.router. Real Postgres via the `client`
fixture. Seeds roles/permissions directly through the ORM (bypassing the seed
script's own idempotency logic, which isn't the thing under test here) and
issues a real session cookie the same way auth's own router tests do."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.auth.models import User
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole


async def _seed_permission(engine: AsyncEngine, resource: str, action: str) -> int:
    async with engine.begin() as conn:
        result = await conn.execute(
            Permission.__table__.insert().values(resource=resource, action=action, description="x")
        )
        return result.inserted_primary_key[0]


async def _seed_role(engine: AsyncEngine, name: str, *, is_system: bool, permission_ids: list[int]) -> int:
    async with engine.begin() as conn:
        result = await conn.execute(Role.__table__.insert().values(name=name, is_system=is_system))
        role_id = result.inserted_primary_key[0]
        for permission_id in permission_ids:
            await conn.execute(
                RolePermission.__table__.insert().values(role_id=role_id, permission_id=permission_id)
            )
        return role_id


async def _seed_user(engine: AsyncEngine, *, email: str, external_user_id: str) -> int:
    async with engine.begin() as conn:
        result = await conn.execute(
            User.__table__.insert().values(
                email=email,
                name="Test User",
                status="active",
                external_user_id=external_user_id,
                employee_code=None,
                email_confirmed=True,
            )
        )
        return result.inserted_primary_key[0]


async def _grant_role(engine: AsyncEngine, user_id: int, role_id: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(UserRole.__table__.insert().values(user_id=user_id, role_id=role_id))


async def _login_as(client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]) -> int:
    """Seed a user with a role granting exactly `permissions`, and a valid session
    cookie for them, without going through the real DX OAuth flow."""
    from app.core.security import JwtCodec
    from app.modules.auth.config import auth_settings
    from app.modules.auth.constants import AuthCookies

    permission_ids = [await _seed_permission(engine, r, a) for r, a in permissions]
    role_id = await _seed_role(engine, "test-role", is_system=False, permission_ids=permission_ids)
    user_id = await _seed_user(engine, email="perm-test@example.com", external_user_id="dx-perm-test")
    await _grant_role(engine, user_id, role_id)

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": "test-jti"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


class TestRolesRequirePermission:
    async def test_list_roles_without_permission_is_403(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_as(client, engine, permissions=[])

        response = await client.get("/api/v1/rbac/roles")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_list_roles_with_permission_succeeds(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_as(client, engine, permissions=[("role", "read")])

        response = await client.get("/api/v1/rbac/roles")

        body = response.json()
        assert response.status_code == 200
        assert body["success"] is True
        assert any(r["name"] == "test-role" for r in body["data"]["items"])


class TestCreateRole:
    async def test_creates_a_role(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_as(client, engine, permissions=[("role", "create")])

        response = await client.post(
            "/api/v1/rbac/roles", json={"name": "support", "permissionIds": []}
        )

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["name"] == "support"
        assert body["data"]["isSystem"] is False


class TestAssignUserRole:
    async def test_assigns_role_to_target_user(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_as(client, engine, permissions=[("user", "assign_role")])
        target_role_id = await _seed_role(engine, "viewer", is_system=False, permission_ids=[])
        target_user_id = await _seed_user(engine, email="target@example.com", external_user_id="dx-target")

        response = await client.patch(
            f"/api/v1/rbac/users/{target_user_id}/role", json={"roleId": target_role_id}
        )

        assert response.status_code == 200
        async with engine.begin() as conn:
            row = await conn.execute(select(UserRole).where(UserRole.user_id == target_user_id))
            assert row.scalar_one().role_id == target_role_id

    async def test_unknown_target_user_is_404(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_as(client, engine, permissions=[("user", "assign_role")])
        role_id = await _seed_role(engine, "viewer2", is_system=False, permission_ids=[])

        response = await client.patch("/api/v1/rbac/users/999999/role", json={"roleId": role_id})

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "rbac_target_user_not_found"
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && pytest tests/rbac/test_router.py -v`
Expected: PASS (6 tests). If `test_list_roles_without_permission_is_403` fails with a 401 instead of 403, check that `_login_as`'s JWT `sub` matches a real seeded user id and that `require_auth`'s blacklist check isn't rejecting a fresh token — compare against `tests/auth/test_router.py`'s own cookie-setting pattern.

- [ ] **Step 6: `ruff check` + `ruff format --check`**

Run: `ruff check app/modules/rbac app/main.py app/seeds/seed_rbac.py && ruff format --check app/modules/rbac app/seeds/seed_rbac.py`
Expected: `All checks passed!` / `files already formatted`

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/rbac/router.py backend/app/main.py backend/app/seeds/seed_rbac.py backend/tests/rbac/test_router.py
git commit -m "feat(rbac): admin API, app wiring, and idempotent seed script"
```

---

### Task 10: `auth` module cleanup — drop `Department`, `UserRole`, `RoleMapping`

Uses the manual impact map at the top of this plan. Every file below is touched precisely because it appeared in that grep.

**Files:**
- Modify: `backend/app/modules/auth/models.py`
- Modify: `backend/app/modules/auth/constants.py`
- Modify: `backend/app/modules/auth/schemas.py`
- Modify: `backend/app/modules/auth/repository.py`
- Modify: `backend/app/modules/auth/uow.py`
- Modify: `backend/app/modules/auth/rules.py`
- Modify: `backend/tests/auth/test_rules.py`

**Interfaces:**
- Produces: `UserRead` without `role`/`department_id`; `AuthRules` with only `can_login`.

- [ ] **Step 1: `models.py`** — delete the `Department` class entirely; on `User`, delete `role`, `department_id`, `department` (relationship); delete now-unused imports (`ForeignKey` stays for `department_id`? No — remove it if nothing else on `User` uses `ForeignKey`; check before deleting the import).

```python
"""ORM models owned by the auth module. No other module may query these tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.auth.constants import AuthLimits, UserStatus


class User(Base):
    """A user account, synced from a DX profile on every successful login."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(AuthLimits.MAX_EMAIL_LENGTH), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(AuthLimits.MAX_NAME_LENGTH))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False), default=UserStatus.PENDING, index=True
    )
    external_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    employee_code: Mapped[str | None] = mapped_column(
        String(AuthLimits.MAX_EMPLOYEE_CODE_LENGTH), nullable=True
    )
    email_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

(Note: the `Enum` import must stay — `status` still uses it — add `Enum` back to the import line above; it was in the original file's import list.)

- [ ] **Step 2: `constants.py`** — delete `UserRole`, delete `RoleMapping`; keep everything else.

- [ ] **Step 3: `schemas.py`** — delete `DepartmentRead`; on `UserRead`, delete `role`, `department_id`.

```python
"""Schemas for the auth module."""

from datetime import datetime

from app.core.models import FrozenModel
from app.modules.auth.constants import UserStatus


class UserRead(FrozenModel):
    """Representation safe to round trip through the cache. Never includes DX tokens."""

    id: int
    email: str
    name: str
    status: UserStatus
    external_user_id: str | None
    employee_code: str | None
    email_confirmed: bool
    last_login_at: datetime | None
    created_at: datetime
```

- [ ] **Step 4: `repository.py`** — delete `AbstractDepartmentRepository`/`DepartmentRepository` entirely; on `AbstractUserRepository`/`UserRepository`, delete the `role`/`department_id` parameters from `create`/`update_profile` and the corresponding `User(...)`/`row.department_id = ...` lines.

```python
"""Single access path to the auth tables (users)."""

from abc import abstractmethod
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.repository import AbstractRepository
from app.modules.auth.constants import UserStatus
from app.modules.auth.models import User
from app.modules.auth.schemas import UserRead


class AbstractUserRepository(AbstractRepository[UserRead]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def find_by_email(self, email: str) -> UserRead | None:
        """Look up a user by email."""
        raise NotImplementedError

    @abstractmethod
    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        """Look up a user by the DX subject identifier."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Create a new user synced from a DX profile."""
        raise NotImplementedError

    @abstractmethod
    async def update_profile(
        self,
        user_id: int,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Sync an existing user's profile fields from DX. Deliberately excludes
        status: a local admin's suspension must never be silently overwritten by
        the next DX login."""
        raise NotImplementedError

    @abstractmethod
    async def set_last_login(self, user_id: int, at: datetime) -> None:
        """Record the timestamp of a completed login."""
        raise NotImplementedError

    @abstractmethod
    async def set_status(self, user_id: int, status: UserStatus) -> UserRead:
        """Block or unblock a user (Task 12's user.update_status endpoint)."""
        raise NotImplementedError


class UserRepository(AbstractUserRepository):
    """SQLAlchemy implementation. Every read of the users table goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: int) -> UserRead | None:
        """Return one user, or None when it does not exist."""
        row = await self._session.scalar(select(User).where(User.id == entity_id))
        return UserRead.model_validate(row) if row else None

    @database
    async def find_by_email(self, email: str) -> UserRead | None:
        """Look up a user by email."""
        row = await self._session.scalar(select(User).where(User.email == email))
        return UserRead.model_validate(row) if row else None

    @database
    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        """Look up a user by the DX subject identifier."""
        row = await self._session.scalar(select(User).where(User.external_user_id == external_user_id))
        return UserRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[UserRead], int]:
        """Return one page of users together with the total count."""
        rows = await self._session.scalars(select(User).order_by(User.id).limit(limit).offset(offset))
        items = [UserRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(User))
        return items, total or 0

    @database
    async def create(
        self,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Create a new user synced from a DX profile.

        status is set to ACTIVE (not the model's PENDING default): DX is
        this app's identity provider, so a profile it hands back has
        already been authenticated there — see docs/tasks/sso-login.md #5.4.
        """
        row = User(
            email=email,
            name=name,
            status=UserStatus.ACTIVE,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return UserRead.model_validate(row)

    @database
    async def update_profile(
        self,
        user_id: int,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Sync an existing user's profile fields from DX (status untouched)."""
        row = await self._session.get(User, user_id)
        if row is None:
            raise ValueError(f"user {user_id} does not exist")
        row.email = email
        row.name = name
        row.external_user_id = external_user_id
        row.employee_code = employee_code
        row.email_confirmed = email_confirmed
        await self._session.flush()
        await self._session.refresh(row)
        return UserRead.model_validate(row)

    @database
    async def set_last_login(self, user_id: int, at: datetime) -> None:
        """Record the timestamp of a completed login."""
        row = await self._session.get(User, user_id)
        if row is not None:
            row.last_login_at = at
            await self._session.flush()

    @database
    async def set_status(self, user_id: int, status: UserStatus) -> UserRead:
        """Block or unblock a user."""
        row = await self._session.get(User, user_id)
        if row is None:
            raise ValueError(f"user {user_id} does not exist")
        row.status = status
        await self._session.flush()
        await self._session.refresh(row)
        return UserRead.model_validate(row)
```

- [ ] **Step 5: `uow.py`** — delete the `departments` field and its construction.

- [ ] **Step 6: `rules.py`** — delete `resolve_role`; `AuthRules` keeps only `can_login`.

```python
"""Business rules for the auth module."""

from app.core.base.markers import rule
from app.modules.auth.constants import LoginPolicy, UserStatus


class AuthRules:
    """Every business decision about a user."""

    @staticmethod
    @rule
    def can_login(status: UserStatus) -> bool:
        """Decide whether a user in this status is allowed to complete a login."""
        return status not in LoginPolicy.BLOCKED_STATUSES
```

- [ ] **Step 7: Update `tests/auth/test_rules.py`** — delete the `test_resolve_role` test and its `UserRole` import/parametrize block entirely; keep `test_can_login` as-is.

- [ ] **Step 8: Run what still passes**

Run: `cd backend && pytest tests/auth/test_rules.py -v`
Expected: PASS (3 tests — only `test_can_login`'s parametrizations). `tests/auth/test_services.py` and `test_router.py` will still fail here — that's expected, they're fixed in Tasks 11–12.

- [ ] **Step 9: `ruff check`**

Run: `ruff check app/modules/auth/models.py app/modules/auth/constants.py app/modules/auth/schemas.py app/modules/auth/repository.py app/modules/auth/uow.py app/modules/auth/rules.py`
Expected: `All checks passed!`

- [ ] **Step 10: Commit**

```bash
git add backend/app/modules/auth/models.py backend/app/modules/auth/constants.py backend/app/modules/auth/schemas.py backend/app/modules/auth/repository.py backend/app/modules/auth/uow.py backend/app/modules/auth/rules.py backend/tests/auth/test_rules.py
git commit -m "refactor(auth): drop Department and UserRole enum, role now lives in rbac"
```

---

### Task 11: `auth` services — wire rbac, drop role/department logic

**Files:**
- Modify: `backend/app/modules/auth/services/sync_external_user.py`
- Modify: `backend/app/modules/auth/services/issue_tokens.py`
- Modify: `backend/app/modules/auth/services/authenticate.py`
- Modify: `backend/app/modules/auth/dependencies.py`
- Modify: `backend/tests/auth/test_services.py`

**Interfaces:**
- Consumes: `AssignDefaultRole` (Task 7) via `rbac.public.get_rbac_api`/direct construction.
- Produces: `SyncExternalUser.execute(profile) -> (UserRead, bool)` (unchanged signature, changed body); `AuthenticateWithDx.__init__` gains an `assign_default_role: AssignDefaultRole` parameter.

- [ ] **Step 1: Rewrite `sync_external_user.py`**

```python
"""Use case: upsert the local User from a DX profile."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.dx_core.client import DxUserProfile
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork


class SyncExternalUser(AbstractUseCase):
    """Sync a DX /oauth2/userinfo profile into the local users table.

    Role assignment is no longer this use case's job — see
    AuthenticateWithDx, which grants the default rbac role only for a brand
    new user, right after this returns is_new=True.
    """

    def __init__(self, uow: AbstractAuthUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, profile: DxUserProfile) -> tuple[UserRead, bool]:
        """Return (user, is_new)."""
        existing = await self._uow.users.find_by_external_id(profile.sub)
        if existing is None:
            existing = await self._uow.users.find_by_email(profile.email)

        if existing is None:
            user = await self._uow.users.create(
                email=profile.email,
                name=profile.name,
                external_user_id=profile.sub,
                employee_code=profile.employee_code,
                email_confirmed=profile.email_verified,
            )
            return user, True

        user = await self._uow.users.update_profile(
            existing.id,
            email=profile.email,
            name=profile.name,
            external_user_id=profile.sub,
            employee_code=profile.employee_code,
            email_confirmed=profile.email_verified,
        )
        return user, False
```

- [ ] **Step 2: Remove the JWT role claim in `issue_tokens.py`**

Change the access-token claims line from:
```python
{"sub": str(user.id), "role": user.role.value, "type": "access", "jti": uuid.uuid4().hex},
```
to:
```python
{"sub": str(user.id), "type": "access", "jti": uuid.uuid4().hex},
```
No other line changes — `UserRead` no longer has `.role`, and nothing decodes this claim today (verified in the impact map: `get_current_user` only reads `sub`/`jti`/`type`). Permissions are resolved live via rbac on every request instead of trusted from a token, which is also the correct behavior once roles are editable mid-session.

- [ ] **Step 3: Wire `AssignDefaultRole` into `authenticate.py`**

```python
"""Use case: complete the DX OAuth2 callback (docs/tasks/sso-login.md #4 Step 4)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.events import EventBus
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.events import UserCreated, UserLoggedIn
from app.modules.auth.exceptions import UserBlocked
from app.modules.auth.rules import AuthRules
from app.modules.auth.schemas import UserRead
from app.modules.auth.services.issue_tokens import AppTokenSet, IssueTokens
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.rbac.services.assign_default_role import AssignDefaultRole


@dataclass(frozen=True)
class DxLoginResult:
    """What the callback route needs to finish the HTTP response."""

    user: UserRead
    tokens: AppTokenSet


class AuthenticateWithDx(AbstractUseCase):
    """Exchange code -> profile -> sync user -> policy check -> store DX tokens -> issue session.

    For a brand new user, also grants the seeded default rbac role
    (assign_default_role) in the same transaction this use case commits —
    replaces the old DX-role-code auto-mapping.
    """

    def __init__(
        self,
        uow: AbstractAuthUnitOfWork,
        dx_tokens: AbstractDxTokenRepository,
        dx_client: DxCoreClient,
        sync_user: SyncExternalUser,
        issue_tokens: IssueTokens,
        events: EventBus,
        assign_default_role: AssignDefaultRole,
    ) -> None:
        self._uow = uow
        self._dx_tokens = dx_tokens
        self._dx_client = dx_client
        self._sync_user = sync_user
        self._issue_tokens = issue_tokens
        self._events = events
        self._assign_default_role = assign_default_role

    @use_case
    async def execute(self, code: str, code_verifier: str) -> DxLoginResult:
        token = await self._dx_client.exchange_code(code, code_verifier)
        profile = await self._dx_client.fetch_userinfo(token.access_token)

        user, is_new = await self._sync_user.execute(profile)
        if not AuthRules.can_login(user.status):
            raise UserBlocked()

        if is_new:
            await self._assign_default_role.execute(user.id)

        expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)
        await self._dx_tokens.save(user.id, token, expires_at=expires_at)
        await self._uow.users.set_last_login(user.id, datetime.now(UTC))
        await self._uow.commit()

        tokens = await self._issue_tokens.execute(user)

        if is_new:
            await self._events.publish(UserCreated(user_id=user.id, email=user.email))
        await self._events.publish(UserLoggedIn(user_id=user.id))

        return DxLoginResult(user=user, tokens=tokens)
```

- [ ] **Step 4: Wire the new collaborator in `dependencies.py`**

In `backend/app/modules/auth/dependencies.py`, add the import and thread it through `get_authenticate_with_dx`:

```python
from app.modules.rbac.dependencies import get_assign_default_role
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
```

```python
async def get_authenticate_with_dx(
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    dx_tokens: AbstractDxTokenRepository = Depends(get_dx_token_repository),
    dx_client: DxCoreClient = Depends(get_dx_core_client),
    sync_user: SyncExternalUser = Depends(get_sync_external_user),
    issue_tokens: IssueTokens = Depends(get_issue_tokens),
    events: EventBus = Depends(get_event_bus),
    assign_default_role: AssignDefaultRole = Depends(get_assign_default_role),
) -> AuthenticateWithDx:
    """Provide the DX OAuth2 callback use case."""
    return AuthenticateWithDx(uow, dx_tokens, dx_client, sync_user, issue_tokens, events, assign_default_role)
```

This makes `auth` depend on `rbac` for this one wiring — the only direction allowed (rbac never imports auth's internals, only its `public.py`; here it's the reverse: auth's composition root depends on rbac's, both at the `dependencies.py`/service level, not through models/repository — acceptable per rule #1, which forbids reaching into `models.py`/`repository.py`, not `services`/`dependencies.py` wiring between two modules that both already have a legitimate reason to know about each other for this one call).

- [ ] **Step 5: Update `tests/auth/test_services.py`**

Remove `FakeDepartmentRepository` entirely; remove `departments` from `FakeAuthUnitOfWork`; remove `role`/`department_id` from `FakeUserRepository.create`/`update_profile`/`UserRead` construction; add a `FakeAssignDefaultRole` collaborator; update `TestSyncExternalUser` and `TestAuthenticateWithDx` accordingly:

```python
"""Unit tests for the auth module's use cases. No database, no Redis, no HTTP —
every collaborator is a fake implementing the module's own Abstract* contract."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import jwt
import pytest

from app.core.events import DomainEvent
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.dx_core.client import DxDepartment, DxUserProfile
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCacheNamespaces, UserStatus
from app.modules.auth.events import UserCreated, UserLoggedIn
from app.modules.auth.exceptions import UserBlocked
from app.modules.auth.repository import AbstractUserRepository
from app.modules.auth.schemas import UserRead
from app.modules.auth.services.authenticate import AuthenticateWithDx
from app.modules.auth.services.issue_tokens import IssueTokens
from app.modules.auth.services.logout import LogoutUser
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.rbac.services.assign_default_role import AssignDefaultRole


class FakeUserRepository(AbstractUserRepository):
    """In-memory stand-in for UserRepository. No SQLAlchemy, no session."""

    def __init__(self) -> None:
        self._rows: dict[int, UserRead] = {}
        self._next_id = 1
        self.last_login_calls: list[tuple[int, datetime]] = []

    async def get_by_id(self, entity_id: int) -> UserRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[UserRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def find_by_email(self, email: str) -> UserRead | None:
        return next((u for u in self._rows.values() if u.email == email), None)

    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        return next((u for u in self._rows.values() if u.external_user_id == external_user_id), None)

    async def create(
        self,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        user = UserRead(
            id=self._next_id,
            email=email,
            name=name,
            status=UserStatus.ACTIVE,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
            last_login_at=None,
            created_at=datetime.now(UTC),
        )
        self._rows[user.id] = user
        self._next_id += 1
        return user

    async def update_profile(
        self,
        user_id: int,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        existing = self._rows[user_id]
        updated = existing.model_copy(
            update={
                "email": email,
                "name": name,
                "external_user_id": external_user_id,
                "employee_code": employee_code,
                "email_confirmed": email_confirmed,
            }
        )
        self._rows[user_id] = updated
        return updated

    async def set_last_login(self, user_id: int, at: datetime) -> None:
        self.last_login_calls.append((user_id, at))
        existing = self._rows.get(user_id)
        if existing is not None:
            self._rows[user_id] = existing.model_copy(update={"last_login_at": at})

    async def set_status(self, user_id: int, status: UserStatus) -> UserRead:
        existing = self._rows[user_id]
        updated = existing.model_copy(update={"status": status})
        self._rows[user_id] = updated
        return updated

    def seed_blocked(self, user: UserRead) -> None:
        """Test helper: insert a user directly (e.g. already BLOCKED)."""
        self._rows[user.id] = user
        self._next_id = max(self._next_id, user.id + 1)


class FakeAuthUnitOfWork(AbstractAuthUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeAssignDefaultRole(AssignDefaultRole):
    """Records calls instead of touching a real rbac uow — constructed without
    calling super().__init__ since it never needs a real AbstractRbacUnitOfWork."""

    def __init__(self) -> None:  # noqa: PLW0231 -- deliberately skips AssignDefaultRole.__init__, see docstring
        self.calls: list[int] = []

    async def execute(self, user_id: int) -> None:
        self.calls.append(user_id)


@dataclass
class FakeDxTokenRow:
    """Stand-in for app.integrations.dx_core.models.DxToken — plaintext, no encryption."""

    user_id: int
    access_token: str
    refresh_token: str
    expires_at: datetime


class FakeDxTokenRepository(AbstractDxTokenRepository):
    """In-memory stand-in for DxTokenRepository. Stores tokens as plaintext —
    encryption is DxTokenRepository's own concern, not this use case's."""

    def __init__(self) -> None:
        self._rows: dict[int, FakeDxTokenRow] = {}
        self.saved: list[tuple[int, str]] = []
        self.cleared: list[int] = []

    async def get_by_user_id(self, user_id: int) -> FakeDxTokenRow | None:
        return self._rows.get(user_id)

    async def save(self, user_id: int, token, *, expires_at: datetime) -> None:
        self._rows[user_id] = FakeDxTokenRow(
            user_id=user_id,
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_at=expires_at,
        )
        self.saved.append((user_id, token.access_token))

    async def clear(self, user_id: int) -> None:
        self._rows.pop(user_id, None)
        self.cleared.append(user_id)

    def decrypt_access_token(self, row: FakeDxTokenRow) -> str:
        return row.access_token


@dataclass
class FakeDxTokenSet:
    """Stand-in for app.integrations.dx_core.client.DxTokenSet."""

    access_token: str = "dx-access-token"
    refresh_token: str = "dx-refresh-token"
    expires_in: int = 3600
    scope: str = ""


class FakeDxCoreClient:
    """Fake DX HTTP client per the acceptance criterion — no real network I/O."""

    def __init__(self, token: FakeDxTokenSet | None = None, profile: DxUserProfile | None = None) -> None:
        self.token = token or FakeDxTokenSet()
        self.profile = profile
        self.revoked: list[str] = []

    async def exchange_code(self, code: str, code_verifier: str) -> FakeDxTokenSet:
        return self.token

    async def fetch_userinfo(self, access_token: str) -> DxUserProfile:
        assert self.profile is not None
        return self.profile

    async def revoke(self, token: str) -> None:
        self.revoked.append(token)


@dataclass
class FakeEventBus:
    """Records every published event instead of dispatching to handlers."""

    published: list[DomainEvent] = field(default_factory=list)

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)


def _dx_profile(**overrides) -> DxUserProfile:
    defaults = {
        "sub": "dx-sub-1",
        "email": "alice@example.com",
        "name": "Alice",
        "department": DxDepartment(code="mkt", name="Marketing"),
        "roles": ["manager"],
        "employee_code": "E001",
        "email_verified": True,
    }
    defaults.update(overrides)
    return DxUserProfile(**defaults)


class TestSyncExternalUser:
    """SyncExternalUser: upsert a local user from a DX profile."""

    async def test_creates_new_user(self) -> None:
        uow = FakeAuthUnitOfWork()
        use_case = SyncExternalUser(uow)

        user, is_new = await use_case.execute(_dx_profile())

        assert is_new is True
        assert user.email == "alice@example.com"
        assert user.status is UserStatus.ACTIVE

    async def test_second_login_updates_profile_without_touching_status(self) -> None:
        uow = FakeAuthUnitOfWork()
        use_case = SyncExternalUser(uow)
        first, _ = await use_case.execute(_dx_profile())

        second, is_new = await use_case.execute(_dx_profile(name="Alice B."))

        assert is_new is False
        assert second.id == first.id
        assert second.name == "Alice B."

    async def test_matches_existing_user_by_email_when_external_id_unseen(self) -> None:
        """A user created before this DX link existed (or under a different sub)
        is matched by email so login doesn't create a duplicate account."""
        uow = FakeAuthUnitOfWork()
        existing = await uow.users.create(
            email="alice@example.com",
            name="Alice (legacy)",
            external_user_id="stale-sub",
            employee_code=None,
            email_confirmed=False,
        )
        use_case = SyncExternalUser(uow)

        user, is_new = await use_case.execute(_dx_profile(sub="dx-sub-new"))

        assert is_new is False
        assert user.id == existing.id
        assert user.external_user_id == "dx-sub-new"


class TestIssueTokens:
    """IssueTokens: mint this app's own session JWTs, independent of DX's own tokens."""

    async def test_issues_access_and_refresh_tokens_with_expected_claims(self) -> None:
        user = UserRead(
            id=42,
            email="bob@example.com",
            name="Bob",
            status=UserStatus.ACTIVE,
            external_user_id="sub",
            employee_code=None,
            email_confirmed=True,
            last_login_at=None,
            created_at=datetime.now(UTC),
        )

        tokens = await IssueTokens().execute(user)

        access_claims = jwt.decode(tokens.access_token, auth_settings.JWT_SECRET, algorithms=["HS256"])
        refresh_claims = jwt.decode(tokens.refresh_token, auth_settings.JWT_SECRET, algorithms=["HS256"])
        assert access_claims["sub"] == "42"
        assert "role" not in access_claims
        assert access_claims["type"] == "access"
        assert refresh_claims["sub"] == "42"
        assert refresh_claims["type"] == "refresh"
        assert access_claims["jti"] != refresh_claims["jti"]


class TestAuthenticateWithDx:
    """AuthenticateWithDx: exchange code -> profile -> sync -> policy -> tokens -> session."""

    def _build(self, *, profile: DxUserProfile, token: FakeDxTokenSet | None = None):
        uow = FakeAuthUnitOfWork()
        dx_tokens = FakeDxTokenRepository()
        dx_client = FakeDxCoreClient(token=token, profile=profile)
        events = FakeEventBus()
        assign_default_role = FakeAssignDefaultRole()
        use_case = AuthenticateWithDx(
            uow, dx_tokens, dx_client, SyncExternalUser(uow), IssueTokens(), events, assign_default_role
        )
        return use_case, uow, dx_tokens, events, assign_default_role

    async def test_new_user_login_grants_default_role_and_publishes_both_events(self) -> None:
        use_case, uow, dx_tokens, events, assign_default_role = self._build(profile=_dx_profile())

        result = await use_case.execute("auth-code", "verifier")

        assert result.user.email == "alice@example.com"
        assert assign_default_role.calls == [result.user.id]
        assert dx_tokens.saved == [(result.user.id, "dx-access-token")]
        assert uow.commits == 1
        published_types = [type(e) for e in events.published]
        assert published_types == [UserCreated, UserLoggedIn]

    async def test_returning_user_login_does_not_grant_default_role_again(self) -> None:
        use_case, uow, _dx_tokens, events, assign_default_role = self._build(profile=_dx_profile())
        await use_case.execute("first-code", "first-verifier")
        events.published.clear()
        assign_default_role.calls.clear()

        await use_case.execute("second-code", "second-verifier")

        assert assign_default_role.calls == []
        assert [type(e) for e in events.published] == [UserLoggedIn]

    async def test_blocked_user_raises_before_storing_tokens_or_committing(self) -> None:
        uow = FakeAuthUnitOfWork()
        blocked = UserRead(
            id=7,
            email="blocked@example.com",
            name="Blocked",
            status=UserStatus.BLOCKED,
            external_user_id="dx-sub-1",
            employee_code=None,
            email_confirmed=True,
            last_login_at=None,
            created_at=datetime.now(UTC),
        )
        uow.users.seed_blocked(blocked)
        dx_tokens = FakeDxTokenRepository()
        events = FakeEventBus()
        use_case = AuthenticateWithDx(
            uow,
            dx_tokens,
            FakeDxCoreClient(profile=_dx_profile(email="blocked@example.com")),
            SyncExternalUser(uow),
            IssueTokens(),
            events,
            FakeAssignDefaultRole(),
        )

        with pytest.raises(UserBlocked):
            await use_case.execute("code", "verifier")

        assert dx_tokens.saved == []
        assert uow.commits == 0
        assert events.published == []


class TestLogoutUser:
    """LogoutUser: best-effort DX revoke, always clear the DX link, blacklist app tokens."""

    def _valid_token(self, *, ttl: int = 3600) -> str:
        return jwt.encode(
            {
                "sub": "1",
                "type": "access",
                "jti": "jti-1",
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int(datetime.now(UTC).timestamp()) + ttl,
            },
            auth_settings.JWT_SECRET,
            algorithm="HS256",
        )

    async def test_revokes_dx_token_clears_link_and_blacklists_both_app_tokens(self, cache_client) -> None:
        dx_tokens = FakeDxTokenRepository()
        await dx_tokens.save(1, FakeDxTokenSet(access_token="plain-dx-token"), expires_at=datetime.now(UTC))
        dx_client = FakeDxCoreClient()
        use_case = LogoutUser(dx_tokens, dx_client, cache_client)
        access = self._valid_token()
        refresh = self._valid_token()

        await use_case.execute(1, access, refresh)

        assert dx_client.revoked == ["plain-dx-token"]
        assert dx_tokens.cleared == [1]
        assert await cache_client.get_json(_blacklist_key(access)) == {"revoked": True}
        assert await cache_client.get_json(_blacklist_key(refresh)) == {"revoked": True}

    async def test_skips_dx_revoke_when_user_never_linked(self, cache_client) -> None:
        dx_tokens = FakeDxTokenRepository()
        dx_client = FakeDxCoreClient()
        use_case = LogoutUser(dx_tokens, dx_client, cache_client)

        await use_case.execute(1, None, None)

        assert dx_client.revoked == []
        assert dx_tokens.cleared == [1]

    async def test_skips_blacklisting_an_unparsable_token(self, cache_client) -> None:
        dx_tokens = FakeDxTokenRepository()
        use_case = LogoutUser(dx_tokens, FakeDxCoreClient(), cache_client)

        await use_case.execute(1, "not-a-jwt", None)  # must not raise


def _blacklist_key(raw_token: str) -> str:
    claims = jwt.decode(raw_token, auth_settings.JWT_SECRET, algorithms=["HS256"])
    return CacheKeyBuilder.session_key(AuthCacheNamespaces.TOKEN_BLACKLIST, claims["jti"])
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && pytest tests/auth/test_services.py -v`
Expected: PASS. `TestLogoutUser`/`FakeDxTokenRepository`/etc. are otherwise unchanged from before — this confirms nothing outside the role/department blast radius broke.

- [ ] **Step 7: `ruff check`**

Run: `ruff check app/modules/auth/services app/modules/auth/dependencies.py tests/auth/test_services.py`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/auth/services backend/app/modules/auth/dependencies.py backend/tests/auth/test_services.py
git commit -m "refactor(auth): wire rbac default-role grant into SSO login, drop role JWT claim"
```

---

### Task 12: `auth` router — `/me` composes rbac, new admin endpoints

**Files:**
- Modify: `backend/app/modules/auth/router.py`
- Modify: `backend/tests/auth/test_router.py`

**Interfaces:**
- Consumes: `RbacApi`/`get_rbac_api` (Task 8), `require_permission` (Task 8).
- Produces: `GET /api/v1/auth/me` response gains `roleName`/`permissions`; new `GET /api/v1/auth/users`, `PATCH /api/v1/auth/users/{id}/status`.

- [ ] **Step 1: Add a `MeResponse` schema**

In `backend/app/modules/auth/schemas.py`, add:

```python
class MeResponse(FrozenModel):
    """/me's response: the user's profile plus their resolved role/permissions."""

    user: UserRead
    role_name: str
    permissions: list[str]
```

- [ ] **Step 2: Update `router.py`'s `/me` endpoint and add the two user-admin endpoints**

The existing import block has:
```python
from app.modules.auth.dependencies import get_authenticate_with_dx, get_logout_user, require_auth
from app.modules.auth.exceptions import UserBlocked
from app.modules.auth.schemas import UserRead
```
Change those three lines to (adding `get_uow`, `CannotBlockLastOwner`, `MeResponse`/`UserStatusUpdate`) and add the four new lines below them:
```python
from app.modules.auth.dependencies import get_authenticate_with_dx, get_logout_user, get_uow, require_auth
from app.modules.auth.exceptions import CannotBlockLastOwner, UserBlocked
from app.modules.auth.schemas import MeResponse, UserRead, UserStatusUpdate
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.auth.constants import UserStatus
from app.modules.rbac.public import RbacApi, get_rbac_api, require_permission
```

```python
@router.get("/me")
async def me(
    user: UserRead = Depends(require_auth), rbac: RbacApi = Depends(get_rbac_api)
) -> ApiResponse[MeResponse]:
    """Return the signed in user's profile plus their role and permissions —
    what the frontend's PermissionProvider seeds from."""
    summary = await rbac.role_summary_for_user(user.id)
    body = MeResponse(user=user, role_name=summary.role_name, permissions=summary.permissions)
    return ApiResponse[MeResponse](success=True, data=body)


@router.get("/users")
async def list_users(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("user", "read")),
) -> ApiResponse[Page[UserRead]]:
    """List users for the admin user-management page."""
    items, total = await uow.users.list_page(pagination.limit, pagination.offset)
    page = Page[UserRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[UserRead]](success=True, data=page)


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    body: UserStatusUpdate,
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    rbac: RbacApi = Depends(get_rbac_api),
    _user: UserRead = Depends(require_permission("user", "update_status")),
) -> ApiResponse[UserRead]:
    """Block or unblock a user. Blocking the last owner is rejected — see rbac's bus-factor rule."""
    if body.status == UserStatus.BLOCKED and await rbac.is_last_owner(user_id):
        raise CannotBlockLastOwner()
    updated = await uow.users.set_status(user_id, body.status)
    await uow.commit()
    return ApiResponse[UserRead](success=True, data=updated)
```

`get_uow` used above is `auth`'s own, newly added to this file's import in this step (it wasn't imported before — `router.py` previously only used `require_auth`/`get_authenticate_with_dx`/`get_logout_user` from `auth.dependencies`). The router does **not** import `rbac`'s own `get_uow` under the same name — both modules' `dependencies.py` happen to export a function called `get_uow`, so `rbac`'s would need aliasing if ever imported directly here (it isn't — only `get_rbac_api`/`require_permission` from `rbac.public` are used).

Also add the two new pieces this step introduces to their owning files: `UserStatusUpdate` to `backend/app/modules/auth/schemas.py` and `CannotBlockLastOwner` (plus `CANNOT_BLOCK_LAST_OWNER = "auth_cannot_block_last_owner"` on `auth`'s `ErrorCode`) to `backend/app/modules/auth/exceptions.py` and `constants.py` respectively — both shown in the code blocks further below in this task.

Add the missing schema and exception:

```python
# schemas.py — add alongside MeResponse
class UserStatusUpdate(FrozenModel):
    """Request body for PATCH /auth/users/{id}/status."""

    status: UserStatus
```

```python
# exceptions.py — add alongside the existing ones
class CannotBlockLastOwner(ForbiddenError):
    """Raised when blocking this user would leave zero users holding the owner role."""

    code = ErrorCode.CANNOT_BLOCK_LAST_OWNER  # add CANNOT_BLOCK_LAST_OWNER = "auth_cannot_block_last_owner" to ErrorCode
    message = "This is the last user with the owner role — reassign it before blocking them"
```

- [ ] **Step 3: Update `tests/auth/test_router.py`'s `/me` assertion**

The existing `test_me_returns_the_signed_in_users_profile` reads `body["data"]["email"]` directly — with the new `MeResponse` envelope, the path is now `body["data"]["user"]["email"]`. Update:

```python
    async def test_me_returns_the_signed_in_users_profile(self, client: AsyncClient, engine) -> None:
        _install_fake_dx_client(_profile(email="dave@example.com", sub="dx-sub-router-2"))
        state = await _start_and_get_state(client)
        callback = await client.get(
            "/api/v1/auth/oauth/dx/callback", params={"code": "auth-code", "state": state}
        )
        client.cookies.update(callback.cookies)

        response = await client.get("/api/v1/auth/me")

        body = response.json()
        assert response.status_code == 200
        assert body["success"] is True
        assert body["data"]["user"]["email"] == "dave@example.com"
        assert body["data"]["roleName"] == "member"
        assert body["data"]["permissions"] == []
```

This last assertion (`permissions == []`) only passes once the `member` role is actually seeded with no permissions — this test needs the rbac seed data present. Add a fixture-level seed:

```python
# tests/conftest.py — add, used by any test needing the default roles seeded
@pytest.fixture(autouse=True)
async def _seed_default_roles(engine) -> None:
    from app.modules.rbac.models import Role

    async with engine.begin() as conn:
        for name, is_system in (("owner", True), ("admin", True), ("member", True)):
            await conn.execute(
                Role.__table__.insert().values(name=name, is_system=is_system)
            )
    yield
```

`autouse=True` on `engine` (session-scoped) would only run once and get truncated away by the `client` fixture's per-test cleanup — scope this fixture to `client` instead so it reseeds every test:

```python
@pytest.fixture(autouse=True)
async def _seed_default_roles(client) -> None:  # noqa: ARG001 -- depended on for its side effect, not its value
    """Every test gets the three default roles present, matching what
    `python -m app.seeds.seed_rbac` guarantees in a real deploy."""
    from app.modules.rbac.models import Role

    async with client._transport.app.state.engine... 
```

Stop — `client` fixture doesn't expose the engine directly in a way worth threading through like this. Simpler: make the new fixture depend on `engine` directly (not `client`), but run its insert **after** `client`'s per-test truncation would otherwise wipe it — since fixture teardown order is LIFO and `_seed_default_roles` needs to insert *before* the test body runs but *after* any per-test cleanup from a **previous** test, the correct scope is function-scoped, depending on `client` to guarantee it runs within that test's already-truncated-and-ready schema, but only inserting — not depending on `client`'s return value:

```python
@pytest.fixture(autouse=True)
async def _seed_default_roles(engine, client) -> None:
    """Every test gets the three default roles present, matching what
    `python -m app.seeds.seed_rbac` guarantees in a real deploy. Depends on
    `client` (not just `engine`) purely for ordering — `client` truncates
    all tables in its own teardown, and fixture setup for the *next* test
    runs after that teardown, so depending on it here guarantees this insert
    happens after the table is already clean."""
    from app.modules.rbac.models import Role

    async with engine.begin() as conn:
        for name, is_system in (("owner", True), ("admin", True), ("member", True)):
            await conn.execute(Role.__table__.insert().values(name=name, is_system=is_system))
```

Place this fixture in `backend/tests/conftest.py`, `autouse=True` so every test across every module gets the three default roles without repeating the insert per test file.

- [ ] **Step 4: Run the full auth + rbac suite**

Run: `cd backend && pytest tests/auth tests/rbac -v`
Expected: PASS, all files.

- [ ] **Step 5: `ruff check` + `ruff format --check` + `lint-imports` (if configured — Task list note: this repo has no `lint-imports` config yet; if still absent, note it as a pre-existing gap per `checklist.md`'s own instruction to flag rather than skip, don't add the tool as part of this task)**

Run: `ruff check app/modules/auth app/modules/rbac tests/auth tests/rbac && ruff format --check app/modules/auth app/modules/rbac`
Expected: `All checks passed!` / `files already formatted`

- [ ] **Step 6: Full backend test suite**

Run: `pytest -v`
Expected: PASS, every test file in `backend/tests/`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/auth/router.py backend/app/modules/auth/schemas.py backend/app/modules/auth/exceptions.py backend/tests/auth/test_router.py backend/tests/conftest.py
git commit -m "feat(auth): /me composes role+permissions, add user list/block/unblock endpoints"
```

---

## Self-review notes (done during writing, not a separate pass)

- **Spec coverage:** data model (Tasks 1–2), permission catalog + seeded roles (Tasks 2, 9), bus-factor rule (Task 4, exercised in Tasks 7/12), `role.update` partial-lock nuance (Task 7's `UpdateRole`), backend flow changes / `SyncExternalUser`+`/me` composition (Tasks 11–12), router-thinness constraint (called out in Global Constraints and Task 9's router docstring) — all covered. Frontend, migration-data-backfill-if-users-exist, and the risks section are out of this plan's scope by design (backend-only; frontend is a separate plan).
- **Placeholder scan:** no TODO/TBD; every step has real code.
- **Type consistency:** `RoleRead`/`PermissionRead`/`RoleSummary` field names and `AbstractRbacUnitOfWork.{roles,permissions,user_roles}` names are identical across Tasks 3, 5, 6, 7, 8, 9. `AssignRole`'s `UserLookup` type alias is defined once (Task 7) and consumed with the same signature in Task 8.

## Execution note on Task 12 Step 3

The fixture-design detour left in Step 3 above is deliberate, not an editing mistake — it shows the reasoning the executor needs (why `engine`-scoped alone is wrong, why `client`-only is wrong) because getting fixture ordering wrong here silently produces flaky tests (roles present sometimes, wiped other times) that are hard to diagnose after the fact. Implement the final `_seed_default_roles(engine, client)` version only.
