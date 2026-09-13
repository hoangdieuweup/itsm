# Per-Project, Per-Resource Permission Variance (Project Roles) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user hold different `resource.action` capabilities per project (editor on environments, viewer on links, differently in every project) without retrofitting the global `rbac.Role`/`UserRole`/`RolePermission` tables.

**Architecture:** A new, additive `ProjectRole`/`ProjectRolePermission` pair inside the existing `projects` module, FK'd to the existing `permissions` catalog table by id (no duplicate catalog, no cross-module Python import). `ProjectMember` gains a nullable `project_role_id`. A single new dependency, `require_project_permission(resource, action)`, replaces the two-gate `require_permission(...)` + `require_project_membership()` pairing on every project-scoped route: it computes the caller's **effective permission set as the union of their global permissions and their project role's permissions**, bounded by a code-defined allowlist (`ProjectScopedPermissionCatalog.ASSIGNABLE`) so a project role can never mint global-only power (`user.update_status`, `project.delete`, `project_role.*` itself, etc.).

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic + pytest + testcontainers (backend); Next.js App Router + TanStack Query + Zod + Vitest (frontend). Same stack as every other module in this repo — no new dependency.

**Spec:** `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md`, section `## Feature — Per-Project, Per-Resource Permission Variance (Project Roles)` (the plan argues from that spec's 8 Decisions D1-D8; this document is the bite-sized execution of it — read both).

## Global Constraints

- **D1 (union, not narrow):** a project role GRANTS on top of global permissions, never restricts them. `project_role_id = NULL` on a member row means "global baseline only" — byte-for-byte today's behavior.
- **D2 (bounded allowlist):** only `ProjectScopedPermissionCatalog.ASSIGNABLE` atoms are ever assignable to a project role: `(project,read)`, `(project,update)`, `(environment,create)`, `(environment,read)`, `(environment,update)`, `(environment,delete)`, `(project_link,read)`, `(project_link,manage)`, `(project_member,read)`. Everything else — `project.delete`, `project.manage_all`, `project_member.manage`, both `project_role.*` atoms, every non-project resource — is permanently excluded, enforced in a pure function AND at the API boundary.
- **D3:** `GET /projects` has no `project_id` path param and can never be project-scoped — the global `project:read` atom stays a hard prerequisite for a collaborator to discover a project at all.
- **D4:** the 15 already-membership-gated routes in `projects/router.py` (confirmed by direct count — see Task 8) collapse from `require_permission(R,A)` + `require_project_membership*()` into one `require_project_permission*(R,A)`.
- **D5 is already shipped** — `RbacResources.PROJECT_LINK`/`PROJECT_MEMBER` already exist in `backend/app/modules/rbac/constants.py` and `projects/router.py` already gates links/members routes with them (confirmed by direct read — this plan does NOT need to introduce these resources, only migrate their routes' *dependency shape*, not their *resource*).
- **D6:** `ProjectRolePermission.permission_id` FKs the `permissions` table by name only — no Python import of `rbac.models`.
- **D7:** the frontend `<CanInProject>`/`useCanInProject` primitive lives in `entities/permission`, not `modules/projects` (other modules will need it without a forbidden module→module import).
- **D8:** the frontend project-permission provider falls back to the global permission set while its query is pending or errored — never suspends, never flickers a gated control off (the effective set is always a superset of global).
- **Two disclosed, intentional behavior changes** (not regressions): (a) the error code on the 15 migrated routes changes from `rbac_permission_denied` to `projects_project_permission_denied`; (b) none — D5's resource split already shipped, so there is no additional "existing roles don't automatically gain X" gap left to disclose for *this* plan (that gap was already taken by whoever shipped D5).
- **Standing constraint:** every migration/manual-verification step targets the `itsm_test` sibling database on the shared Postgres server — never the live `itsm` database.

---

## Task 1: `ProjectRoleRules` — the pure union/allowlist functions (D1 + D2, TDD from the ground up)

**Files:**
- Create: `backend/app/modules/projects/constants.py` (extend existing file)
- Modify: `backend/app/modules/projects/rules.py`
- Test: `backend/tests/projects/test_rules.py` (new file — no rules tests exist yet for this module)

**Interfaces:**
- Produces: `ProjectScopedPermissionCatalog.ASSIGNABLE: frozenset[tuple[str, str]]`; `ProjectRoleRules.assignable_keys() -> frozenset[tuple[str, str]]`; `ProjectRoleRules.rejects_unassignable(keys: list[tuple[str, str]]) -> list[tuple[str, str]]` (returns the rejected subset — empty means all accepted); `ProjectRoleRules.effective_permissions(global_keys: frozenset[str], project_keys: frozenset[str]) -> frozenset[str]` (both args already `"resource.action"` strings, not tuples — this function is the union boundary, D1's fork expressed as one line).

- [ ] **Step 1: Write the failing tests**

```python
"""tests/projects/test_rules.py — pure decisions, no I/O."""

from app.modules.projects.rules import ProjectRoleRules


class TestAssignableKeys:
    def test_includes_environment_update_but_not_project_delete(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("environment", "update") in keys
        assert ("project", "delete") not in keys
        assert ("project", "manage_all") not in keys
        assert ("project_member", "manage") not in keys
        assert ("project_role", "read") not in keys
        assert ("project_role", "manage") not in keys
        assert ("user", "update_status") not in keys


class TestRejectsUnassignable:
    def test_accepts_every_assignable_key(self) -> None:
        assert ProjectRoleRules.rejects_unassignable([("environment", "update"), ("project", "read")]) == []

    def test_rejects_user_update_status(self) -> None:
        rejected = ProjectRoleRules.rejects_unassignable([("environment", "update"), ("user", "update_status")])
        assert rejected == [("user", "update_status")]

    def test_rejects_project_delete(self) -> None:
        assert ProjectRoleRules.rejects_unassignable([("project", "delete")]) == [("project", "delete")]


class TestEffectivePermissions:
    def test_null_project_role_yields_exactly_the_global_set(self) -> None:
        global_keys = frozenset({"project.read", "environment.read"})
        assert ProjectRoleRules.effective_permissions(global_keys, frozenset()) == global_keys

    def test_project_role_adds_to_global_not_replaces_it(self) -> None:
        global_keys = frozenset({"project.read"})
        project_keys = frozenset({"environment.update"})
        result = ProjectRoleRules.effective_permissions(global_keys, project_keys)
        assert result == frozenset({"project.read", "environment.update"})

    def test_overlapping_keys_do_not_duplicate(self) -> None:
        global_keys = frozenset({"environment.read"})
        project_keys = frozenset({"environment.read"})
        assert ProjectRoleRules.effective_permissions(global_keys, project_keys) == frozenset({"environment.read"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/projects/test_rules.py -v`
Expected: FAIL — `ImportError: cannot import name 'ProjectRoleRules'` (the class doesn't exist as a rules-holder yet; `ProjectsRules` does, but not this one) and `AttributeError` on `ProjectScopedPermissionCatalog`.

- [ ] **Step 3: Write the minimal implementation**

Add to `backend/app/modules/projects/constants.py` (after `ProjectAuditActions`, keeping the existing file's every current line unchanged):

```python
class ProjectScopedPermissionCatalog:
    """The subset of the global rbac.Permission catalog a ProjectRole may
    ever grant. Bounded deliberately (see D2 in the spec): project.delete
    (cascades every downstream Cloudflare/Loki/alerting row), project.
    manage_all, project_member.manage, and both project_role.* atoms are
    permanently excluded — managing roles/members and deleting a project
    always require a GLOBAL atom, never a project-scoped one, closing the
    mint-yourself-more-power loop a naive union would open."""

    ASSIGNABLE: frozenset[tuple[str, str]] = frozenset(
        {
            ("project", "read"),
            ("project", "update"),
            ("environment", "create"),
            ("environment", "read"),
            ("environment", "update"),
            ("environment", "delete"),
            ("project_link", "read"),
            ("project_link", "manage"),
            ("project_member", "read"),
        }
    )
```

Add to `backend/app/modules/projects/rules.py` (append `ProjectRoleRules` as a second class in the same file — it's a second, related set of pure decisions for the same module, exactly how `CloudflareAccountRules`/`CloudflareDnsRules` coexist in `cloudflare/rules.py`):

```python
from app.modules.projects.constants import ProjectLinkType, ProjectScopedPermissionCatalog


class ProjectRoleRules:
    """Every business decision about project-scoped roles — the D1/D2
    boundary from the spec, expressed as pure functions."""

    @staticmethod
    @rule
    def assignable_keys() -> frozenset[tuple[str, str]]:
        """The bounded set a ProjectRole may ever grant."""
        return ProjectScopedPermissionCatalog.ASSIGNABLE

    @staticmethod
    @rule
    def rejects_unassignable(keys: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Return the subset of keys NOT in the allowlist. Empty = every
        key is acceptable to assign to a project role."""
        assignable = ProjectRoleRules.assignable_keys()
        return [key for key in keys if key not in assignable]

    @staticmethod
    @rule
    def effective_permissions(global_keys: frozenset[str], project_keys: frozenset[str]) -> frozenset[str]:
        """D1: a project role GRANTS on top of the caller's global
        permissions — the union, never a narrowing. Flipping to narrow
        semantics later is a one-line change here (intersection instead
        of union) plus updating this function's own tests."""
        return global_keys | project_keys
```

(The existing `from app.modules.projects.constants import ProjectLinkType` import line already at the top of `rules.py` gets `ProjectScopedPermissionCatalog` added to it — one edit, not a new import block.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/projects/test_rules.py -v`
Expected: PASS, all 8 tests.

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/modules/projects/constants.py app/modules/projects/rules.py tests/projects/test_rules.py
git commit -m "feat(projects): add ProjectRoleRules union/allowlist (D1+D2)"
```

---

## Task 2: `ProjectRole`/`ProjectRolePermission` models + migration

**Files:**
- Modify: `backend/app/modules/projects/models.py`
- Create: `backend/alembic/versions/<new_rev>_create_project_roles_schema.py`

**Interfaces:**
- Consumes: nothing new (pure schema task).
- Produces: `ProjectRole(id, project_id, name, created_at, updated_at)`; `ProjectRolePermission(project_role_id, permission_id)` composite PK; `ProjectMember.project_role_id: UUID | None`.

- [ ] **Step 1: Add the models**

Append to `backend/app/modules/projects/models.py` (after the existing `ProjectMember` class, and add `project_role_id` to `ProjectMember` itself):

```python
class ProjectRole(Base):
    """A role scoped to exactly one project — an assignable bundle of the
    global permission catalog's atoms, restricted to
    ProjectScopedPermissionCatalog.ASSIGNABLE at the service layer."""

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
    module's `permissions` table by table name only (D6) — no Python
    import of app.modules.rbac anywhere in this file."""

    __tablename__ = "project_role_permissions"
    __table_args__ = (PrimaryKeyConstraint("project_role_id", "permission_id"),)

    project_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_roles.id", ondelete="CASCADE")
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE")
    )
```

Modify the existing `ProjectMember` class — add one column after `created_at`:

```python
    project_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_roles.id", ondelete="SET NULL"), nullable=True
    )
```

(`SET NULL`, not `CASCADE` — deleting a project role must degrade its members to global-only, never delete their membership row.)

Add `MAX_PROJECT_ROLE_NAME_LENGTH = 100` to `ProjectLimits` in `constants.py`.

- [ ] **Step 2: Write the migration**

`down_revision = "f4c8b2e91a37"` (confirmed current head via `grep -rL "down_revision = " backend/alembic/versions/*.py` returning only this file — verify this yourself with the same command before writing the file, since another migration may have landed since; if a different file is now the head, use that revision id instead). House style copied exactly from `backend/alembic/versions/f4c8b2e91a37_create_project_members_schema.py`.

```python
"""create_project_roles_schema

Revision ID: <new_rev>
Revises: f4c8b2e91a37
Create Date: 2026-08-25 12:00:00.000000

Adds project-scoped roles: a ProjectRole is an assignable bundle of the
existing global permission catalog's atoms (FK'd by id, no duplicate
catalog), restricted at the service layer to
ProjectScopedPermissionCatalog.ASSIGNABLE. A member's effective
permission set in a project becomes the UNION of their global
permissions and their assigned project role's permissions (see
docs/superpowers/plans/2026-08-25-project-scoped-permissions.md) —
project_role_id is nullable and additive, so every existing
project_members row keeps today's exact behavior until someone
explicitly creates and assigns a role.
"""

import sqlalchemy as sa

from alembic import op

revision = "<new_rev>"
down_revision = "f4c8b2e91a37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("project_roles_project_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("project_roles_pkey")),
        sa.UniqueConstraint("project_id", "name", name="project_roles_project_id_name_key"),
    )
    op.create_index(op.f("project_roles_project_id_idx"), "project_roles", ["project_id"], unique=False)

    op.create_table(
        "project_role_permissions",
        sa.Column("project_role_id", sa.UUID(), nullable=False),
        sa.Column("permission_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_role_id"],
            ["project_roles.id"],
            name=op.f("project_role_permissions_project_role_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("project_role_permissions_permission_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_role_id", "permission_id", name=op.f("project_role_permissions_pkey")
        ),
    )

    op.add_column("project_members", sa.Column("project_role_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("project_members_project_role_id_fkey"),
        "project_members",
        "project_roles",
        ["project_role_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("project_members_project_role_id_fkey"), "project_members", type_="foreignkey"
    )
    op.drop_column("project_members", "project_role_id")
    op.drop_table("project_role_permissions")
    op.drop_index(op.f("project_roles_project_id_idx"), table_name="project_roles")
    op.drop_table("project_roles")
```

- [ ] **Step 3: Verify the migration round-trips against `itsm_test`**

Run (never against the live `itsm` database):
```bash
cd backend
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic upgrade head
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic downgrade -1
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic upgrade head
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic current
```
Expected: final `alembic current` prints `<new_rev> (head)`, no errors at any step.

- [ ] **Step 4: Verify models load cleanly**

Run: `cd backend && uv run mypy app/modules/projects/models.py`
Expected: `Success: no issues found in 1 source file`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/projects/models.py app/modules/projects/constants.py alembic/versions/<new_rev>_create_project_roles_schema.py
git commit -m "feat(projects): add project_roles/project_role_permissions schema"
```

---

## Task 3: `ProjectRoleRead`/`Create`/`Update` schemas + exceptions

**Files:**
- Modify: `backend/app/modules/projects/schemas.py`
- Modify: `backend/app/modules/projects/exceptions.py`
- Modify: `backend/app/modules/projects/constants.py` (ErrorCode + ProjectAuditActions)

**Interfaces:**
- Consumes: `rbac.public.PermissionRead` (added in Task 4 — this task's `ProjectRoleRead.permissions` field type depends on it, so implement Task 4's export first if executing out of order; the plan lists Task 4 next specifically so this dependency is satisfied).
- Produces: `ProjectRoleRead{id, project_id, name, permissions: list[PermissionRead], created_at, updated_at}`; `ProjectRoleCreate{name: str, permission_ids: list[UUID] = []}`; `ProjectRoleUpdate{name: str | None, permission_ids: list[UUID] | None}`; `ProjectMemberRoleAssign{project_role_id: UUID | None}`; `ProjectPermissionSetRead{project_id: UUID, permissions: list[str]}`; `ProjectRoleNotFound`, `DuplicateProjectRoleName`, `PermissionNotProjectAssignable`, `ProjectPermissionDenied`.

- [ ] **Step 1: Add the error codes and audit actions**

In `constants.py`'s `ErrorCode`, append:
```python
    PROJECT_ROLE_NOT_FOUND = "projects_project_role_not_found"
    DUPLICATE_PROJECT_ROLE_NAME = "projects_duplicate_project_role_name"
    PERMISSION_NOT_PROJECT_ASSIGNABLE = "projects_permission_not_project_assignable"
    PROJECT_PERMISSION_DENIED = "projects_project_permission_denied"
```
In `ProjectAuditActions`, append:
```python
    PROJECT_ROLE_CREATED = "PROJECT_ROLE_CREATED"
    PROJECT_ROLE_UPDATED = "PROJECT_ROLE_UPDATED"
    PROJECT_ROLE_DELETED = "PROJECT_ROLE_DELETED"
    MEMBER_ROLE_ASSIGNED = "MEMBER_ROLE_ASSIGNED"
```

- [ ] **Step 2: Add the schemas**

Append to `schemas.py` (add `from app.modules.rbac.public import PermissionRead` to the top imports — this is the one, deliberate cross-module import this module makes, same tier as `projects/access.py` already importing `rbac.public.RbacApi`):

```python
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
```

Also extend the existing `ProjectMemberRead`, adding two optional fields:
```python
    project_role_id: UUID | None = None
    project_role_name: str | None = None
```

- [ ] **Step 3: Add the exceptions**

Append to `exceptions.py`:
```python
class ProjectRoleNotFound(NotFoundError):
    """Raised when no project role matches the requested id."""

    code = ErrorCode.PROJECT_ROLE_NOT_FOUND
    message = "Project role not found"


class DuplicateProjectRoleName(ConflictError):
    """Raised when a project already has a role with the requested name."""

    code = ErrorCode.DUPLICATE_PROJECT_ROLE_NAME
    message = "This project already has a role with that name"


class PermissionNotProjectAssignable(ConflictError):
    """Raised when a project role's requested permissions include one
    outside ProjectScopedPermissionCatalog.ASSIGNABLE (D2)."""

    code = ErrorCode.PERMISSION_NOT_PROJECT_ASSIGNABLE
    message = "One or more permissions cannot be assigned to a project role"


class ProjectPermissionDenied(ForbiddenError):
    """Raised when the caller's effective project permission set (global
    UNION project role, D1) does not include the required resource.action.
    Projects-owned rather than reusing rbac's PermissionDenied — that
    class isn't exported through rbac/public.py, and cross-module error
    reuse would break the module-owns-its-errors rule."""

    code = ErrorCode.PROJECT_PERMISSION_DENIED
    message = "You do not have this permission on this project"
```

- [ ] **Step 4: Verify it imports cleanly**

Run: `cd backend && uv run python -c "from app.modules.projects import schemas, exceptions"`
Expected: no output, exit code 0. (`PermissionRead` won't yet be exported from `rbac.public` if Task 4 hasn't run — if this fails with `ImportError: cannot import name 'PermissionRead'`, do Task 4 first, then return here.)

- [ ] **Step 5: Commit**

```bash
git add app/modules/projects/schemas.py app/modules/projects/exceptions.py app/modules/projects/constants.py
git commit -m "feat(projects): add ProjectRole schemas and exceptions"
```

---

## Task 4: `rbac` module additions — catalog rows + facade methods (additive only)

**Files:**
- Modify: `backend/app/modules/rbac/constants.py`
- Modify: `backend/app/modules/rbac/public.py`
- Test: `backend/tests/rbac/test_constants.py` (extend existing file)

**Interfaces:**
- Consumes: `AbstractPermissionRepository.find_by_ids`/`list_all` (confirmed already existing at `rbac/repository.py:148,153,181,189` — no change needed there).
- Produces: `RbacResources.PROJECT_ROLE = "project_role"`; `RbacApi.get_permissions_by_ids(ids: list[UUID]) -> list[PermissionRead]`; `RbacApi.list_permission_catalog() -> list[PermissionRead]`; `PermissionRead` now exported from `rbac.public`.

- [ ] **Step 1: Write the failing test**

The existing `backend/tests/rbac/test_constants.py` has `test_catalog_includes_alert_rule_and_incident_permissions` asserting `len(RbacPermissionCatalog.CATALOG) == 33`. Update it (this is a legitimate, expected growth — the catalog now includes 2 more atoms — not a broken test):

```python
    def test_catalog_includes_alert_rule_and_incident_permissions(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        for action in ("create", "read", "update", "delete"):
            assert ("alert_rule", action) in resources_actions
        for action in ("create", "read", "acknowledge", "resolve"):
            assert ("incident", action) in resources_actions
        assert ("incident", "update") not in resources_actions
        assert ("incident", "delete") not in resources_actions
        assert ("project", "manage_all") in resources_actions
        assert ("project_role", "read") in resources_actions
        assert ("project_role", "manage") in resources_actions
        assert len(RbacPermissionCatalog.CATALOG) == 35
```

(Run `cd backend && uv run python -c "from app.modules.rbac.constants import RbacPermissionCatalog; print(len(RbacPermissionCatalog.CATALOG))"` first to confirm the actual current count before hardcoding — the file may have grown further since this plan was written; use `current_count + 2` as the new assertion, not a blindly copied `35`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/rbac/test_constants.py -v`
Expected: FAIL — `AssertionError` (count mismatch) and `assert ("project_role", "read") in resources_actions` fails.

- [ ] **Step 3: Write the minimal implementation**

In `rbac/constants.py`'s `RbacPermissionCatalog.CATALOG`, append two rows (near the existing `# ── Projects ──` section, alongside `project_member`/`project_link`):
```python
        ("project_role", "read", "permissions.project_role.read"),
        ("project_role", "manage", "permissions.project_role.manage"),
```
In `RbacResources`, add:
```python
    PROJECT_ROLE = "project_role"
```

In `rbac/public.py`: add `PermissionRead` to the existing `from app.modules.rbac.schemas import RoleSummary` import line (making it `from app.modules.rbac.schemas import PermissionRead, RoleSummary`) and to `__all__`. Add two new `@facade` methods to `RbacApi` (after `has_permission`):

```python
    @facade
    async def get_permissions_by_ids(self, ids: list[UUID]) -> list[PermissionRead]:
        """Resolve permission ids to their resource.action + description —
        used by a project role's editor UI and by union-permission
        resolution (see projects/access.py)."""
        return await self._uow.permissions.find_by_ids(ids)

    @facade
    async def list_permission_catalog(self) -> list[PermissionRead]:
        """Return the full, fixed permission catalog — backs the project-
        role editor's assignable-permissions picker."""
        return await self._uow.permissions.list_all()
```

(`self._uow.permissions` — confirm this attribute name on `AbstractRbacUnitOfWork` by reading `rbac/uow.py` before writing this step for real; if the attribute is named differently, e.g. `self._uow.permission_repo`, use the real name.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/rbac/test_constants.py -v && uv run mypy app/modules/rbac/`
Expected: PASS; `Success: no issues found`.

- [ ] **Step 5: Re-seed and commit**

```bash
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run python -m app.seeds.seed_rbac
git add app/modules/rbac/constants.py app/modules/rbac/public.py tests/rbac/test_constants.py
git commit -m "feat(rbac): add project_role catalog atoms and permission-resolution facade methods"
```

---

## Task 5: `ProjectRole` repository + uow wiring

**Files:**
- Modify: `backend/app/modules/projects/repository.py`
- Modify: `backend/app/modules/projects/uow.py`
- Test: `backend/tests/projects/test_repository.py` (extend if it exists; if this module has no repository-level test file yet, skip real-Postgres repository tests here — the router integration tests in Task 8 exercise this repository end-to-end, matching how `ProjectMemberRepository` itself shipped with no dedicated repository test file, per direct confirmation in the existing codebase)

**Interfaces:**
- Consumes: `ProjectRole`, `ProjectRolePermission` models (Task 2).
- Produces: `ProjectRoleRow(FrozenModel){id, project_id, name, permission_ids: list[UUID], created_at, updated_at}`; `AbstractProjectRoleRepository` / `ProjectRoleRepository` with `get_by_id`, `list_page`, `list_for_project(project_id) -> list[ProjectRoleRow]`, `find_by_name(project_id, name) -> ProjectRoleRow | None`, `create(*, project_id, name, permission_ids) -> ProjectRoleRow`, `update(project_role_id, *, name, permission_ids) -> ProjectRoleRow`, `delete(project_role_id) -> None`, `permission_ids_for_member(project_id, user_id) -> list[UUID]`; `AbstractProjectMemberRepository.set_project_role(project_id, user_id, project_role_id) -> None` added to the existing contract.

- [ ] **Step 1: Add `ProjectRoleRow` and the abstract contract**

In `repository.py`, alongside the existing `ProjectMemberRow`:
```python
class ProjectRoleRow(FrozenModel):
    """Raw project-role row — permission ids only, no description text
    (the repository has no cross-module knowledge of rbac; enrichment to
    PermissionRead happens in the service layer via RbacApi)."""

    id: UUID
    project_id: UUID
    name: str
    permission_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class AbstractProjectRoleRepository(AbstractRepository[ProjectRoleRow, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_project(self, project_id: UUID) -> list[ProjectRoleRow]:
        raise NotImplementedError

    @abstractmethod
    async def find_by_name(self, project_id: UUID, name: str) -> ProjectRoleRow | None:
        raise NotImplementedError

    @abstractmethod
    async def create(self, *, project_id: UUID, name: str, permission_ids: list[UUID]) -> ProjectRoleRow:
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, project_role_id: UUID, *, name: str | None, permission_ids: list[UUID] | None
    ) -> ProjectRoleRow:
        """None means unchanged; a non-None permission_ids REPLACES the set entirely (same
        replace-set semantics as rbac's RoleRepository.update)."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, project_role_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def permission_ids_for_member(self, project_id: UUID, user_id: UUID) -> list[UUID]:
        """The hot-path join: project_members -> project_role_permissions
        for this specific (project_id, user_id). Empty list if the member
        has no project_role_id or the role grants nothing."""
        raise NotImplementedError
```

- [ ] **Step 2: Implement `ProjectRoleRepository`**

```python
class ProjectRoleRepository(AbstractProjectRoleRepository):
    """SQLAlchemy implementation. Every read/write of project_roles and
    project_role_permissions goes through this class — mirrors how
    RoleRepository owns both roles and role_permissions in rbac."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @helper
    async def _load_by_id(self, project_role_id: UUID) -> ProjectRoleRow | None:
        row = await self._session.get(ProjectRole, project_role_id)
        if row is None:
            return None
        perm_ids = await self._session.scalars(
            select(ProjectRolePermission.permission_id).where(
                ProjectRolePermission.project_role_id == project_role_id
            )
        )
        return ProjectRoleRow(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            permission_ids=list(perm_ids),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @database
    async def get_by_id(self, entity_id: UUID) -> ProjectRoleRow | None:
        return await self._load_by_id(entity_id)

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRoleRow], int]:
        rows = await self._session.scalars(
            select(ProjectRole).order_by(ProjectRole.id).limit(limit).offset(offset)
        )
        items = [await self._load_by_id(row.id) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(ProjectRole))
        return [i for i in items if i is not None], total or 0

    @database
    async def list_for_project(self, project_id: UUID) -> list[ProjectRoleRow]:
        rows = await self._session.scalars(
            select(ProjectRole).where(ProjectRole.project_id == project_id).order_by(ProjectRole.name)
        )
        results = [await self._load_by_id(row.id) for row in rows]
        return [r for r in results if r is not None]

    @database
    async def find_by_name(self, project_id: UUID, name: str) -> ProjectRoleRow | None:
        row = await self._session.scalar(
            select(ProjectRole).where(ProjectRole.project_id == project_id, ProjectRole.name == name)
        )
        return await self._load_by_id(row.id) if row else None

    @database
    async def create(self, *, project_id: UUID, name: str, permission_ids: list[UUID]) -> ProjectRoleRow:
        row = ProjectRole(project_id=project_id, name=name)
        self._session.add(row)
        await self._session.flush()
        for permission_id in permission_ids:
            self._session.add(ProjectRolePermission(project_role_id=row.id, permission_id=permission_id))
        await self._session.flush()
        result = await self._load_by_id(row.id)
        assert result is not None
        return result

    @database
    async def update(
        self, project_role_id: UUID, *, name: str | None, permission_ids: list[UUID] | None
    ) -> ProjectRoleRow:
        row = await self._session.get(ProjectRole, project_role_id)
        if row is None:
            raise ValueError(f"project role {project_role_id} does not exist")
        if name is not None:
            row.name = name
        if permission_ids is not None:
            await self._session.execute(
                delete(ProjectRolePermission).where(ProjectRolePermission.project_role_id == project_role_id)
            )
            for permission_id in permission_ids:
                self._session.add(
                    ProjectRolePermission(project_role_id=project_role_id, permission_id=permission_id)
                )
        await self._session.flush()
        result = await self._load_by_id(project_role_id)
        assert result is not None
        return result

    @database
    async def delete(self, project_role_id: UUID) -> None:
        row = await self._session.get(ProjectRole, project_role_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def permission_ids_for_member(self, project_id: UUID, user_id: UUID) -> list[UUID]:
        member = await self._session.get(ProjectMember, (project_id, user_id))
        if member is None or member.project_role_id is None:
            return []
        rows = await self._session.scalars(
            select(ProjectRolePermission.permission_id).where(
                ProjectRolePermission.project_role_id == member.project_role_id
            )
        )
        return list(rows)
```

Add `delete` (SQLAlchemy `delete`), `ProjectRole`, `ProjectRolePermission` to `repository.py`'s existing imports.

- [ ] **Step 3: Add `set_project_role` to the member repository**

In `AbstractProjectMemberRepository`, add:
```python
    @abstractmethod
    async def set_project_role(self, project_id: UUID, user_id: UUID, project_role_id: UUID | None) -> None:
        """Assign or clear (None) a member's project-scoped role."""
        raise NotImplementedError
```
In `ProjectMemberRepository`:
```python
    @database
    async def set_project_role(self, project_id: UUID, user_id: UUID, project_role_id: UUID | None) -> None:
        row = await self._session.get(ProjectMember, (project_id, user_id))
        if row is not None:
            row.project_role_id = project_role_id
            await self._session.flush()
```
Also add `project_role_id: UUID | None = None` to `ProjectMemberRow`.

- [ ] **Step 4: Wire into `uow.py`**

```python
    project_roles: AbstractProjectRoleRepository
```
added to `AbstractProjectsUnitOfWork`; `self.project_roles = ProjectRoleRepository(session)` added to `ProjectsUnitOfWork.__init__`; `ProjectRoleRepository` added to the existing `from app.modules.projects.repository import (...)` block in `uow.py`.

- [ ] **Step 5: Verify it typechecks**

Run: `cd backend && uv run mypy app/modules/projects/repository.py app/modules/projects/uow.py`
Expected: `Success: no issues found in 2 source files`.

- [ ] **Step 6: Commit**

```bash
git add app/modules/projects/repository.py app/modules/projects/uow.py
git commit -m "feat(projects): add ProjectRoleRepository and wire into ProjectsUnitOfWork"
```

---

## Task 6: `resolve_project_permissions` — the union grant (D1's runtime home)

**Files:**
- Modify: `backend/app/modules/projects/access.py`
- Modify: `backend/app/modules/projects/schemas.py` (add `ProjectPermissionGrant`)
- Test: `backend/tests/projects/test_access.py` (new file)

**Interfaces:**
- Consumes: `resolve_project_membership` (unchanged, existing), `RbacApi.role_summary_for_user` (existing, already returns flat `resource.action` strings), `RbacApi.get_permissions_by_ids` (Task 4), `uow.project_roles.permission_ids_for_member` (Task 5), `ProjectRoleRules.effective_permissions` (Task 1).
- Produces: `ProjectPermissionGrant(FrozenModel){user: UserRead, project_id: UUID, permissions: frozenset[str]}`; `resolve_project_permissions(project_id, user, rbac_api, uow) -> ProjectPermissionGrant`.

- [ ] **Step 1: Write the failing tests**

```python
"""tests/projects/test_access.py — resolve_project_permissions, real Fakes, no DB."""

from uuid import uuid4

import pytest

from app.modules.projects.access import resolve_project_membership, resolve_project_permissions
from app.modules.projects.exceptions import InsufficientProjectAccess
from app.modules.users.public import UserRead
from tests.projects.test_services import ACTOR_EMAIL, ACTOR_ID, FakeProjectsUnitOfWork, FakeRbacApi


class TestResolveProjectPermissions:
    async def test_null_project_role_yields_exactly_the_global_permission_set(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=["project.read"])

        grant = await resolve_project_permissions(project.id, user, rbac_api, uow)

        assert grant.permissions == frozenset({"project.read"})

    async def test_project_role_adds_environment_update_beyond_global_read_only(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        role_perm_id = uuid4()
        role = await uow.project_roles.create(project_id=project.id, name="env-editor", permission_ids=[role_perm_id])
        await uow.project_members.set_project_role(project.id, ACTOR_ID, role.id)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(
            manage_all=False,
            global_permissions=["project.read"],
            catalog_by_id={role_perm_id: "environment.update"},
        )

        grant = await resolve_project_permissions(project.id, user, rbac_api, uow)

        assert grant.permissions == frozenset({"project.read", "environment.update"})

    async def test_non_member_without_manage_all_is_rejected(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        user = UserRead.model_construct(id=uuid4(), email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=[])

        with pytest.raises(InsufficientProjectAccess):
            await resolve_project_permissions(project.id, user, rbac_api, uow)

    async def test_manage_all_bypasses_membership_but_grant_is_still_just_their_global_set(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        user = UserRead.model_construct(id=uuid4(), email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=True, global_permissions=["project.manage_all"])

        grant = await resolve_project_permissions(project.id, user, rbac_api, uow)

        assert grant.permissions == frozenset({"project.manage_all"})
```

(`FakeRbacApi` needs extending in Task 8's step for `test_services.py` — this test file imports it from there rather than duplicating it, matching the existing convention of one Fake set per module reused across test files in this repo. If Task 6 is executed before the `FakeRbacApi` extension lands, extend it here first — see Task 8 Step 1 for the exact shape, and land that extension as part of THIS task's Step 3 instead if sequencing this way is more convenient; either order is fine as long as the extension lands before both test files run.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/projects/test_access.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_project_permissions'`.

- [ ] **Step 3: Extend `FakeRbacApi` (shared by `test_services.py` and `test_access.py`)**

In `tests/projects/test_services.py`, change the existing `FakeRbacApi`:
```python
class FakeRbacApi:
    """Duck-typed stand-in for app.modules.rbac.public.RbacApi — only the
    methods this module's services actually call."""

    def __init__(
        self,
        *,
        manage_all: bool,
        global_permissions: list[str] | None = None,
        catalog_by_id: dict[UUID, str] | None = None,
    ) -> None:
        self._manage_all = manage_all
        self._global_permissions = global_permissions or []
        self._catalog_by_id = catalog_by_id or {}

    async def has_permission(self, user_id, resource, action) -> bool:
        return self._manage_all

    async def role_summary_for_user(self, user_id):
        from app.modules.rbac.schemas import RoleSummary

        return RoleSummary(roles=[], permissions=self._global_permissions, role_name=None)

    async def get_permissions_by_ids(self, ids: list[UUID]):
        from app.modules.rbac.schemas import PermissionRead

        return [
            PermissionRead(id=pid, resource=key.split(".")[0], action=key.split(".")[1], description_key="x")
            for pid, key in self._catalog_by_id.items()
            if pid in ids
        ]

    async def list_permission_catalog(self):
        from app.modules.rbac.schemas import PermissionRead

        return [
            PermissionRead(id=pid, resource=key.split(".")[0], action=key.split(".")[1], description_key="x")
            for pid, key in self._catalog_by_id.items()
        ]
```
Keeping `manage_all` keyword-only and every existing call site (`FakeRbacApi(manage_all=True)` etc. in `test_services.py`) compiling unchanged — the two new params default to empty.

- [ ] **Step 4: Write `resolve_project_permissions`**

Add `ProjectPermissionGrant` to `schemas.py`:
```python
class ProjectPermissionGrant(FrozenModel):
    """The caller's resolved, effective 'resource.action' set inside one
    project — global permissions UNIONed with their project role's grants
    (D1), bounded by ProjectScopedPermissionCatalog.ASSIGNABLE on the way
    IN (enforced when a role is created/updated, Task 7), not here."""

    user: UserRead
    project_id: UUID
    permissions: frozenset[str]
```
(Add `from app.modules.users.public import UserRead` to `schemas.py`'s imports.)

Append to `access.py`:
```python
async def resolve_project_permissions(
    project_id: UUID, user: UserRead, rbac_api: RbacApi, uow: AbstractProjectsUnitOfWork
) -> ProjectPermissionGrant:
    """Membership (or project:manage_all) first — the same gate
    resolve_project_membership already enforces — then compute the
    effective permission set: the caller's global permissions UNIONed
    with whatever their assigned ProjectRole grants inside this project
    (D1). manage_all bypasses MEMBERSHIP only, never adds to the
    permission set itself — a manage_all holder's grant is still just
    their own global permissions."""
    await resolve_project_membership(project_id, user, rbac_api, uow)

    summary = await rbac_api.role_summary_for_user(user.id)
    global_keys = frozenset(summary.permissions)

    role_permission_ids = await uow.project_roles.permission_ids_for_member(project_id, user.id)
    project_permissions = await rbac_api.get_permissions_by_ids(role_permission_ids)
    project_keys = frozenset(f"{p.resource}.{p.action}" for p in project_permissions)

    effective = ProjectRoleRules.effective_permissions(global_keys, project_keys)
    return ProjectPermissionGrant(user=user, project_id=project_id, permissions=effective)
```
(Add `from app.modules.projects.rules import ProjectRoleRules` and `from app.modules.projects.schemas import ProjectPermissionGrant` to `access.py`'s imports.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/projects/test_access.py tests/projects/test_services.py -v`
Expected: PASS — the new tests, and every pre-existing `test_services.py` test still passes unmodified (proves the `FakeRbacApi` extension didn't break the existing `manage_all`-only call sites).

- [ ] **Step 6: Commit**

```bash
git add app/modules/projects/access.py app/modules/projects/schemas.py tests/projects/test_access.py tests/projects/test_services.py
git commit -m "feat(projects): add resolve_project_permissions (union grant, D1)"
```

---

## Task 7: Project-role CRUD services + assign-member-role service

**Files:**
- Create: `backend/app/modules/projects/services/create_project_role.py`
- Create: `backend/app/modules/projects/services/update_project_role.py`
- Create: `backend/app/modules/projects/services/delete_project_role.py`
- Create: `backend/app/modules/projects/services/list_project_roles.py`
- Create: `backend/app/modules/projects/services/assign_member_project_role.py`
- Create: `backend/app/modules/projects/services/list_assignable_permissions.py`
- Modify: `backend/app/modules/projects/services/list_project_members.py` (enrich with role name)
- Test: extend `backend/tests/projects/test_services.py`

**Interfaces:**
- Consumes: `ProjectRoleRules.rejects_unassignable` (Task 1), `AbstractProjectRoleRepository` (Task 5), `RbacApi.get_permissions_by_ids`/`list_permission_catalog` (Task 4).
- Produces: `CreateProjectRole(uow, rbac_api, audit_api).execute(project_id, name, permission_ids, *, actor_id, actor_email) -> ProjectRoleRead`; `UpdateProjectRole(...).execute(project_role_id, *, name, permission_ids, actor_id, actor_email) -> ProjectRoleRead`; `DeleteProjectRole(uow, audit_api).execute(project_role_id, *, actor_id, actor_email) -> None`; `ListProjectRoles(uow, rbac_api).execute(project_id) -> list[ProjectRoleRead]`; `AssignMemberProjectRole(uow, audit_api).execute(project_id, target_user_id, project_role_id, *, actor_id, actor_email) -> None`; `ListAssignablePermissions(rbac_api).execute() -> list[PermissionRead]`.

- [ ] **Step 1: Write the failing tests**

```python
class TestCreateProjectRole:
    async def test_creates_role_with_assignable_permissions(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        perm_id = uuid4()
        rbac_api = FakeRbacApi(manage_all=False, catalog_by_id={perm_id: "environment.update"})

        role = await CreateProjectRole(uow, rbac_api, FakeAuditApi()).execute(
            project.id, "env-editor", [perm_id], actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert role.name == "env-editor"
        assert role.permissions[0].resource == "environment"

    async def test_rejects_non_assignable_permission(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        perm_id = uuid4()
        rbac_api = FakeRbacApi(manage_all=False, catalog_by_id={perm_id: "user.update_status"})

        with pytest.raises(PermissionNotProjectAssignable):
            await CreateProjectRole(uow, rbac_api, FakeAuditApi()).execute(
                project.id, "sneaky", [perm_id], actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

    async def test_rejects_duplicate_name(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        rbac_api = FakeRbacApi(manage_all=False)
        await CreateProjectRole(uow, rbac_api, FakeAuditApi()).execute(
            project.id, "editor", [], actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        with pytest.raises(DuplicateProjectRoleName):
            await CreateProjectRole(uow, rbac_api, FakeAuditApi()).execute(
                project.id, "editor", [], actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

    async def test_rejects_unknown_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        with pytest.raises(ProjectNotFound):
            await CreateProjectRole(uow, FakeRbacApi(manage_all=False), FakeAuditApi()).execute(
                uuid4(), "x", [], actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestAssignMemberProjectRole:
    async def test_assigns_role_and_invalidates_nothing_server_side(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        role = await uow.project_roles.create(project_id=project.id, name="editor", permission_ids=[])

        await AssignMemberProjectRole(uow, FakeAuditApi()).execute(
            project.id, ACTOR_ID, role.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        member = await uow.project_members.get_by_id((project.id, ACTOR_ID))
        assert member.project_role_id == role.id

    async def test_clears_role_when_none(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        role = await uow.project_roles.create(project_id=project.id, name="editor", permission_ids=[])
        await uow.project_members.set_project_role(project.id, ACTOR_ID, role.id)

        await AssignMemberProjectRole(uow, FakeAuditApi()).execute(
            project.id, ACTOR_ID, None, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        member = await uow.project_members.get_by_id((project.id, ACTOR_ID))
        assert member.project_role_id is None

    async def test_rejects_role_from_a_different_project(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project_a = await uow.projects.create(name="A", description=None, created_by=None)
        project_b = await uow.projects.create(name="B", description=None, created_by=None)
        await uow.project_members.add(project_b.id, ACTOR_ID)
        role_on_a = await uow.project_roles.create(project_id=project_a.id, name="editor", permission_ids=[])

        with pytest.raises(ProjectRoleNotFound):
            await AssignMemberProjectRole(uow, FakeAuditApi()).execute(
                project_b.id, ACTOR_ID, role_on_a.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/projects/test_services.py -k "ProjectRole or AssignMemberProjectRole" -v`
Expected: FAIL — `ImportError` on every new service class.

- [ ] **Step 3: Write the minimal implementations**

`services/create_project_role.py`:
```python
"""Create a role scoped to one project."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import DuplicateProjectRoleName, PermissionNotProjectAssignable, ProjectNotFound
from app.modules.projects.rules import ProjectRoleRules
from app.modules.projects.schemas import ProjectRoleRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacApi


class CreateProjectRole(AbstractUseCase):
    """Create a project role. Router gates this with require_project_permission
    (PROJECT_ROLE, MANAGE) — project_role.manage is never itself project-
    assignable (D2), so this always requires a global atom."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, rbac_api: RbacApi, audit_api: AuditApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, project_id: UUID, name: str, permission_ids: list[UUID], *, actor_id: UUID, actor_email: str
    ) -> ProjectRoleRead:
        project = await self._uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFound()

        existing = await self._uow.project_roles.find_by_name(project_id, name)
        if existing is not None:
            raise DuplicateProjectRoleName()

        permissions = await self._rbac_api.get_permissions_by_ids(permission_ids)
        rejected = ProjectRoleRules.rejects_unassignable([(p.resource, p.action) for p in permissions])
        if rejected:
            raise PermissionNotProjectAssignable()

        row = await self._uow.project_roles.create(project_id=project_id, name=name, permission_ids=permission_ids)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.PROJECT_ROLE_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Project role '{name}' created on '{project.name}'",
            project_id=project.id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return ProjectRoleRead(
            id=row.id, project_id=row.project_id, name=row.name, permissions=permissions,
            created_at=row.created_at, updated_at=row.updated_at,
        )
```

`services/update_project_role.py` — same shape as `update_project.py`/`RoleRepository.update`'s None-means-unchanged pattern; resolves the existing row first (`ProjectRoleNotFound` if missing), re-validates `permission_ids` via `ProjectRoleRules.rejects_unassignable` only when `permission_ids is not None`, calls `uow.project_roles.update(...)`, commits, audits `PROJECT_ROLE_UPDATED`.

`services/delete_project_role.py` — resolves + `ProjectRoleNotFound`, calls `uow.project_roles.delete(...)` (the `ON DELETE SET NULL` FK degrades members automatically), commits, audits `PROJECT_ROLE_DELETED`.

`services/list_project_roles.py`:
```python
"""List a project's roles, enriched with each permission's resource/action/description."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import ProjectNotFound
from app.modules.projects.schemas import ProjectRoleRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork
from app.modules.rbac.public import RbacApi


class ListProjectRoles(AbstractUseCase):
    def __init__(self, uow: AbstractProjectsUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, project_id: UUID) -> list[ProjectRoleRead]:
        project = await self._uow.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFound()

        rows = await self._uow.project_roles.list_for_project(project_id)
        result: list[ProjectRoleRead] = []
        for row in rows:
            permissions = await self._rbac_api.get_permissions_by_ids(row.permission_ids)
            result.append(
                ProjectRoleRead(
                    id=row.id, project_id=row.project_id, name=row.name, permissions=permissions,
                    created_at=row.created_at, updated_at=row.updated_at,
                )
            )
        return result
```

`services/assign_member_project_role.py`:
```python
"""Assign (or clear) a member's project-scoped role."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.projects.constants import ProjectAuditActions
from app.modules.projects.exceptions import ProjectRoleNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class AssignMemberProjectRole(AbstractUseCase):
    """Router gates this with require_project_permission(PROJECT_MEMBER,
    MANAGE) — project_member.manage is never project-assignable (D2), so
    this always requires a global atom, closing the escalation loop."""

    def __init__(self, uow: AbstractProjectsUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        project_id: UUID,
        target_user_id: UUID,
        project_role_id: UUID | None,
        *,
        actor_id: UUID,
        actor_email: str,
    ) -> None:
        if project_role_id is not None:
            role = await self._uow.project_roles.get_by_id(project_role_id)
            if role is None or role.project_id != project_id:
                raise ProjectRoleNotFound()

        await self._uow.project_members.set_project_role(project_id, target_user_id, project_role_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=ProjectAuditActions.MEMBER_ROLE_ASSIGNED,
            severity=AuditSeverity.INFO,
            message=f"User {target_user_id}'s project role on {project_id} set to {project_role_id}",
            project_id=project_id,
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
```

`services/list_assignable_permissions.py`:
```python
"""List the permission catalog subset a project role may ever grant."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.rules import ProjectRoleRules
from app.modules.rbac.public import PermissionRead, RbacApi


class ListAssignablePermissions(AbstractUseCase):
    """Backs the project-role editor's checkbox grid WITHOUT requiring the
    global permission:read atom GET /rbac/permissions demands — a project
    admin managing only their own project's roles shouldn't need
    system-wide catalog-read access."""

    def __init__(self, rbac_api: RbacApi) -> None:
        self._rbac_api = rbac_api

    @use_case
    async def execute(self) -> list[PermissionRead]:
        catalog = await self._rbac_api.list_permission_catalog()
        assignable = ProjectRoleRules.assignable_keys()
        return [p for p in catalog if (p.resource, p.action) in assignable]
```

Modify `services/list_project_members.py`'s enrichment loop to also populate `project_role_id`/`project_role_name` on each `ProjectMemberRead` (resolve the role's name via a `dict[UUID, str]` built once from `uow.project_roles.list_for_project(project_id)` before the member loop, avoiding N+1 role lookups — this is the one place in this task worth a small optimization since it's already an N+1-shaped enrichment loop for users).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/projects/test_services.py -v`
Expected: PASS, full file (pre-existing + new tests).

- [ ] **Step 5: Commit**

```bash
git add app/modules/projects/services/ tests/projects/test_services.py
git commit -m "feat(projects): add project role CRUD and member-role-assignment services"
```

---

## Task 8: `dependencies.py` — `require_project_permission` + wiring; `router.py` — 6 new routes + 15 migrated

**Files:**
- Modify: `backend/app/modules/projects/dependencies.py`
- Modify: `backend/app/modules/projects/router.py`
- Test: extend `backend/tests/projects/test_router.py`

**Interfaces:**
- Consumes: `resolve_project_permissions` (Task 6), all Task 7 services.
- Produces: `require_project_permission(resource, action)`, `require_project_permission_for_environment(resource, action)`, `require_project_permission_for_link(resource, action)`, `require_project_membership_for_project_role()` — all `Depends` factories; 6 new routes; 15 routes migrated off the two-gate pattern.

- [ ] **Step 1: Add the new dependency factories**

Append to `dependencies.py` (alongside the existing three `require_project_membership*` factories, which **stay untouched** — `GET /projects/{id}/permissions` still uses the plain `require_project_membership()`):

```python
from app.modules.projects.access import resolve_project_permissions  # add to existing import line
from app.modules.projects.exceptions import ProjectPermissionDenied, ProjectRoleNotFound  # extend existing import
from app.modules.projects.schemas import ProjectPermissionGrant


def require_project_permission(resource: str, action: str):
    """Return a dependency that 403s unless the caller's effective
    permission set in project_id (global UNION project role, D1) includes
    resource.action. Replaces the old require_permission(...) +
    require_project_membership() pairing for the 15 routes migrated in
    this task (D4) — two sequential gates cannot express union."""

    async def check(
        project_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> ProjectPermissionGrant:
        user = auth_api.current_user()
        grant = await resolve_project_permissions(project_id, user, rbac_api, uow)
        if f"{resource}.{action}" not in grant.permissions:
            raise ProjectPermissionDenied()
        return grant

    return check


def require_project_permission_for_environment(resource: str, action: str):
    """Same as require_project_permission, keyed by environment_id."""

    async def check(
        environment_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> ProjectPermissionGrant:
        user = auth_api.current_user()
        environment = await uow.environments.get_by_id(environment_id)
        if environment is None:
            raise EnvironmentNotFound()
        grant = await resolve_project_permissions(environment.project_id, user, rbac_api, uow)
        if f"{resource}.{action}" not in grant.permissions:
            raise ProjectPermissionDenied()
        return grant

    return check


def require_project_permission_for_link(resource: str, action: str):
    """Same as require_project_permission, keyed by link_id."""

    async def check(
        link_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> ProjectPermissionGrant:
        user = auth_api.current_user()
        link = await uow.project_links.get_by_id(link_id)
        if link is None:
            raise ProjectLinkNotFound()
        grant = await resolve_project_permissions(link.project_id, user, rbac_api, uow)
        if f"{resource}.{action}" not in grant.permissions:
            raise ProjectPermissionDenied()
        return grant

    return check


def require_project_membership_for_project_role():
    """Resolves project_role_id (path) -> project_id, then the plain
    binary membership check — used by PATCH/DELETE /project-roles/{id},
    which are also gated by the global project_role:manage atom (Layer 1)
    since project_role.* is never in ASSIGNABLE."""

    async def check(
        project_role_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    ) -> None:
        user = auth_api.current_user()
        role = await uow.project_roles.get_by_id(project_role_id)
        if role is None:
            raise ProjectRoleNotFound()
        await resolve_project_membership(role.project_id, user, rbac_api, uow)

    return check
```

Plus 6 new provider functions (`get_create_project_role`, `get_update_project_role`, `get_delete_project_role`, `get_list_project_roles`, `get_assign_member_project_role`, `get_list_assignable_permissions`) — same one-line `async def get_x(uow=Depends(get_uow), ...) -> X: return X(...)` shape as every existing provider in this file.

- [ ] **Step 2: Migrate the 15 routes (mechanical — one dependency swap each)**

For each of the following in `router.py`, replace `_user: UserRead = Depends(require_permission(R, A))` + `_membership: None = Depends(require_project_membership())` with a single `grant: ProjectPermissionGrant = Depends(require_project_permission(R, A))` (or `_grant: ProjectPermissionGrant = ...` for handlers that don't need `user.id`/`user.email`). Where the handler currently uses `user.id`/`user.email` (routes 2, 3, 14, 15 below), rebind to `grant.user.id`/`grant.user.email`:

| # | Route | New dependency |
|---|---|---|
| 1 | `GET /projects/{id}` | `require_project_permission(RbacResources.PROJECT, RbacActions.READ)` |
| 2 | `PATCH /projects/{id}` | `require_project_permission(RbacResources.PROJECT, RbacActions.UPDATE)` — bind as `grant`, use `grant.user.id`/`grant.user.email` |
| 3 | `DELETE /projects/{id}` | `require_project_permission(RbacResources.PROJECT, RbacActions.DELETE)` — bind as `grant` |
| 4 | `GET /projects/{id}/environments` | `require_project_permission(RbacResources.ENVIRONMENT, RbacActions.READ)` |
| 5 | `POST /projects/{id}/environments` | `require_project_permission(RbacResources.ENVIRONMENT, RbacActions.CREATE)` — bind as `grant` |
| 6 | `GET /environments/{id}` | `require_project_permission_for_environment(RbacResources.ENVIRONMENT, RbacActions.READ)` |
| 7 | `PATCH /environments/{id}` | `require_project_permission_for_environment(RbacResources.ENVIRONMENT, RbacActions.UPDATE)` — bind as `grant` |
| 8 | `DELETE /environments/{id}` | `require_project_permission_for_environment(RbacResources.ENVIRONMENT, RbacActions.DELETE)` — bind as `grant` |
| 9 | `GET /projects/{id}/links` | `require_project_permission(RbacResources.PROJECT_LINK, RbacActions.READ)` |
| 10 | `POST /projects/{id}/links` | `require_project_permission(RbacResources.PROJECT_LINK, RbacActions.MANAGE)` |
| 11 | `PATCH /links/{id}` | `require_project_permission_for_link(RbacResources.PROJECT_LINK, RbacActions.MANAGE)` |
| 12 | `DELETE /links/{id}` | `require_project_permission_for_link(RbacResources.PROJECT_LINK, RbacActions.MANAGE)` |
| 13 | `GET /projects/{id}/members` | `require_project_permission(RbacResources.PROJECT_MEMBER, RbacActions.READ)` |
| 14 | `POST /projects/{id}/members` | `require_project_permission(RbacResources.PROJECT_MEMBER, RbacActions.MANAGE)` — bind as `grant` |
| 15 | `DELETE /projects/{id}/members/{user_id}` | `require_project_permission(RbacResources.PROJECT_MEMBER, RbacActions.MANAGE)` — bind as `grant` |

`POST /projects` and `GET /projects` (routes without a `project_id` path segment) are **not touched** — D3.

Example (route 2, `update_project`, showing the exact before/after — apply the same shape to every row in the table):
```python
@router.patch("/projects/{project_id}")
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    use_case: UpdateProject = Depends(get_update_project),
    grant: ProjectPermissionGrant = Depends(require_project_permission(RbacResources.PROJECT, RbacActions.UPDATE)),
) -> ApiResponse[ProjectRead]:
    """Rename and/or redescribe a project."""
    project = await use_case.execute(
        project_id, name=body.name, description=body.description,
        actor_id=grant.user.id, actor_email=grant.user.email,
    )
    return ApiResponse[ProjectRead](success=True, data=project)
```

Add `ProjectPermissionGrant` to `router.py`'s import from `app.modules.projects.schemas`; add `require_project_permission`, `require_project_permission_for_environment`, `require_project_permission_for_link` to its import from `app.modules.projects.dependencies`; `require_project_membership`, `require_project_membership_for_environment`, `require_project_membership_for_link` are dropped from that import list entirely (no route uses the bare membership checks anymore except the new self-read route below).

- [ ] **Step 3: Add the 6 new routes**

```python
@router.get("/projects/{project_id}/roles")
async def list_project_roles(
    project_id: UUID,
    use_case: ListProjectRoles = Depends(get_list_project_roles),
    _grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_ROLE, RbacActions.READ)
    ),
) -> ApiResponse[list[ProjectRoleRead]]:
    """List a project's roles."""
    roles = await use_case.execute(project_id)
    return ApiResponse[list[ProjectRoleRead]](success=True, data=roles)


@router.post("/projects/{project_id}/roles")
async def create_project_role(
    project_id: UUID,
    body: ProjectRoleCreate,
    use_case: CreateProjectRole = Depends(get_create_project_role),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_ROLE, RbacActions.MANAGE)
    ),
) -> ApiResponse[ProjectRoleRead]:
    """Create a project-scoped role."""
    role = await use_case.execute(
        project_id, body.name, body.permission_ids, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[ProjectRoleRead](success=True, data=role)


@router.patch("/project-roles/{project_role_id}")
async def update_project_role(
    project_role_id: UUID,
    body: ProjectRoleUpdate,
    use_case: UpdateProjectRole = Depends(get_update_project_role),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT_ROLE, RbacActions.MANAGE)),
    _membership: None = Depends(require_project_membership_for_project_role()),
) -> ApiResponse[ProjectRoleRead]:
    """Rename and/or re-permission a project role."""
    role = await use_case.execute(
        project_role_id, name=body.name, permission_ids=body.permission_ids,
        actor_id=user.id, actor_email=user.email,
    )
    return ApiResponse[ProjectRoleRead](success=True, data=role)


@router.delete("/project-roles/{project_role_id}")
async def delete_project_role(
    project_role_id: UUID,
    use_case: DeleteProjectRole = Depends(get_delete_project_role),
    user: UserRead = Depends(require_permission(RbacResources.PROJECT_ROLE, RbacActions.MANAGE)),
    _membership: None = Depends(require_project_membership_for_project_role()),
) -> ApiResponse[None]:
    """Delete a project role. Members holding it degrade to global-only (ON DELETE SET NULL)."""
    await use_case.execute(project_role_id, actor_id=user.id, actor_email=user.email)
    return ApiResponse[None](success=True)


@router.put("/projects/{project_id}/members/{user_id}/role")
async def assign_member_project_role(
    project_id: UUID,
    user_id: UUID,
    body: ProjectMemberRoleAssign,
    use_case: AssignMemberProjectRole = Depends(get_assign_member_project_role),
    grant: ProjectPermissionGrant = Depends(
        require_project_permission(RbacResources.PROJECT_MEMBER, RbacActions.MANAGE)
    ),
) -> ApiResponse[None]:
    """Assign (or clear, body.projectRoleId=null) a member's project role."""
    await use_case.execute(
        project_id, user_id, body.project_role_id, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[None](success=True)


@router.get("/projects/{project_id}/permissions")
async def get_my_project_permissions(
    project_id: UUID,
    auth_api: AuthApi = Depends(get_auth_api),
    rbac_api: RbacApi = Depends(get_rbac_api),
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _membership: None = Depends(require_project_membership()),
) -> ApiResponse[ProjectPermissionSetRead]:
    """Self-read of the caller's own effective permission set in this
    project — gated by plain membership only (not require_project_
    permission — there's no single resource.action to check here, this
    IS the permission-set read)."""
    user = auth_api.current_user()
    grant = await resolve_project_permissions(project_id, user, rbac_api, uow)
    return ApiResponse[ProjectPermissionSetRead](
        success=True,
        data=ProjectPermissionSetRead(project_id=project_id, permissions=sorted(grant.permissions)),
    )
```

Add `AuthApi`/`get_auth_api` to `router.py`'s imports (needed by the last route), plus every new schema/service/dependency name used above to the existing import blocks.

- [ ] **Step 4: Write the decisive router integration test**

Append to `tests/projects/test_router.py`:

```python
class TestProjectRoleUnionGrant:
    async def test_project_role_grants_environment_update_on_A_only_not_B(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """The whole point of the feature: a collaborator with ZERO global
        environment permissions gets elevated to editor on ONE project via
        a project role, and the grant never leaks to a sibling project."""
        admin_id = await _login_with_permissions(
            client, engine,
            permissions=[
                ("project", "create"), ("environment", "create"),
                ("project_member", "manage"), ("project_role", "manage"),
                ("project", "read"),
            ],
            email="admin@example.com",
        )
        project_a = (await client.post("/api/v1/projects", json={"name": "A"})).json()["data"]
        project_b = (await client.post("/api/v1/projects", json={"name": "B"})).json()["data"]
        env_a = (await client.post(
            f"/api/v1/projects/{project_a['id']}/environments", json={"type": "dev", "name": "dev"}
        )).json()["data"]
        env_b = (await client.post(
            f"/api/v1/projects/{project_b['id']}/environments", json={"type": "dev", "name": "dev"}
        )).json()["data"]

        perms_resp = await client.get("/api/v1/rbac/permissions?limit=200")
        env_update_id = next(
            p["id"] for p in perms_resp.json()["data"]["items"]
            if p["resource"] == "environment" and p["action"] == "update"
        )
        role_resp = await client.post(
            f"/api/v1/projects/{project_a['id']}/roles",
            json={"name": "env-editor", "permissionIds": [env_update_id]},
        )
        assert role_resp.status_code == 200
        role_id = role_resp.json()["data"]["id"]

        collaborator_id = await _login_with_permissions(
            client, engine, permissions=[("project", "read")], email="collaborator@example.com"
        )
        # re-login as admin to add + assign (collaborator has no project_member:manage)
        await _login_with_permissions(
            client, engine,
            permissions=[
                ("project", "create"), ("environment", "create"),
                ("project_member", "manage"), ("project_role", "manage"), ("project", "read"),
            ],
            email="admin@example.com",
        )
        await client.post(f"/api/v1/projects/{project_a['id']}/members", json={"userId": str(collaborator_id)})
        await client.post(f"/api/v1/projects/{project_b['id']}/members", json={"userId": str(collaborator_id)})
        assign_resp = await client.put(
            f"/api/v1/projects/{project_a['id']}/members/{collaborator_id}/role",
            json={"projectRoleId": role_id},
        )
        assert assign_resp.status_code == 200

        await _login_with_permissions(
            client, engine, permissions=[("project", "read")], email="collaborator@example.com"
        )

        update_a = await client.patch(f"/api/v1/environments/{env_a['id']}", json={"name": "renamed"})
        assert update_a.status_code == 200

        update_b = await client.patch(f"/api/v1/environments/{env_b['id']}", json={"name": "renamed"})
        assert update_b.status_code == 403
        assert update_b.json()["error"]["code"] == "projects_project_permission_denied"

        perms_a = await client.get(f"/api/v1/projects/{project_a['id']}/permissions")
        assert "environment.update" in perms_a.json()["data"]["permissions"]
        perms_b = await client.get(f"/api/v1/projects/{project_b['id']}/permissions")
        assert "environment.update" not in perms_b.json()["data"]["permissions"]


class TestProjectRoleAllowlist:
    async def test_rejects_a_non_assignable_permission_at_the_api_boundary(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(
            client, engine,
            permissions=[("project", "create"), ("project_role", "manage"), ("user", "update_status")],
            email="admin2@example.com",
        )
        project = (await client.post("/api/v1/projects", json={"name": "A"})).json()["data"]
        perms_resp = await client.get("/api/v1/rbac/permissions?limit=200")
        sneaky_id = next(
            p["id"] for p in perms_resp.json()["data"]["items"]
            if p["resource"] == "user" and p["action"] == "update_status"
        )

        resp = await client.post(
            f"/api/v1/projects/{project['id']}/roles", json={"name": "sneaky", "permissionIds": [sneaky_id]}
        )

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "projects_permission_not_project_assignable"


class TestProjectRoleBackwardCompatibility:
    async def test_null_project_role_member_still_works_via_global_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(
            client, engine,
            permissions=[("project", "create"), ("environment", "create"), ("environment", "update"), ("project", "read")],
            email="solo@example.com",
        )
        project = (await client.post("/api/v1/projects", json={"name": "A"})).json()["data"]
        env = (await client.post(
            f"/api/v1/projects/{project['id']}/environments", json={"type": "dev", "name": "dev"}
        )).json()["data"]

        resp = await client.patch(f"/api/v1/environments/{env['id']}", json={"name": "renamed"})

        assert resp.status_code == 200
```

(Verify the exact `GET /api/v1/rbac/permissions` route shape — path, pagination param names, response envelope field names like `permissionIds` vs `permission_ids` in the camelCase-serialized JSON body — against `rbac/router.py` and the frontend's existing `CustomModel`/`alias_generator` convention before running this; adjust the literal request/response key casing to match reality if it differs from what's written here.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/projects/test_router.py -v`
Expected: PASS, full file.

- [ ] **Step 6: Run the full backend gate**

Run: `cd backend && ruff check . && ruff format --check . && python scripts/check_module_boundaries.py --strict && uv run lint-imports && uv run mypy app/modules/projects/ app/modules/rbac/ && uv run pytest -q`
Expected: everything green; full suite count grows from the pre-this-feature baseline by the new tests added across Tasks 1-8.

- [ ] **Step 7: Commit**

```bash
git add app/modules/projects/dependencies.py app/modules/projects/router.py tests/projects/test_router.py
git commit -m "feat(projects): require_project_permission — union-gated routes + project-role management endpoints"
```

---

## Task 9: Frontend — `<CanInProject>`/`useCanInProject` primitive (D7 + D8)

**Files:**
- Create: `frontend/src/entities/permission/api/fetchers.ts`
- Create: `frontend/src/entities/permission/api/query-keys.ts`
- Create: `frontend/src/entities/permission/hooks/use-project-permissions.ts`
- Create: `frontend/src/entities/permission/model/project-permission-context.tsx`
- Create: `frontend/src/entities/permission/ui/can-in-project.tsx`
- Modify: `frontend/src/entities/permission/index.ts`
- Modify: `frontend/src/shared/constants/api.ts`
- Test: `frontend/src/entities/permission/ui/can-in-project.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` (`@/shared/lib/api-client`), `API_CONFIG` (`@/shared/constants/api`), the existing `useCan` (fallback per D8).
- Produces: `fetchProjectPermissions(projectId: string): Promise<string[]>`; `projectPermissionsKeys`; `useProjectPermissionsQuery(projectId)`; `ProjectPermissionProvider({projectId, children})`; `useCanInProject(resource: string, action: string): boolean`; `<CanInProject I a children fallback>`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/entities/permission/ui/can-in-project.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PermissionProvider } from "../model/permission-context";
import { ProjectPermissionProvider } from "../model/project-permission-context";
import { CanInProject } from "./can-in-project";

vi.mock("@/shared/lib/api-client", () => ({
  apiFetch: vi.fn(() => Promise.resolve(["environment.update"])),
}));

function renderWithProviders(ui: React.ReactNode, globalPermissions: string[] = []) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <PermissionProvider permissions={globalPermissions as never}>
        <ProjectPermissionProvider projectId="p1">{ui}</ProjectPermissionProvider>
      </PermissionProvider>
    </QueryClientProvider>,
  );
}

describe("CanInProject", () => {
  it("falls back to the global set while the project query is pending", () => {
    renderWithProviders(
      <CanInProject I="update" a="project">
        <div>visible</div>
      </CanInProject>,
      ["project.update"],
    );
    expect(screen.getByText("visible")).toBeInTheDocument();
  });

  it("renders children once the project-scoped permission resolves", async () => {
    renderWithProviders(
      <CanInProject I="update" a="environment">
        <div>editor-only</div>
      </CanInProject>,
    );
    await waitFor(() => expect(screen.getByText("editor-only")).toBeInTheDocument());
  });

  it("renders fallback when neither global nor project set grants it", async () => {
    renderWithProviders(
      <CanInProject I="delete" a="project" fallback={<div>denied</div>}>
        <div>hidden</div>
      </CanInProject>,
    );
    await waitFor(() => expect(screen.getByText("denied")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/entities/permission/ui/can-in-project.test.tsx`
Expected: FAIL — module not found (`../model/project-permission-context`, `./can-in-project`).

- [ ] **Step 3: Write the minimal implementation**

`shared/constants/api.ts`, inside `ENDPOINTS.PROJECTS`, add:
```ts
      PERMISSIONS: (projectId: string) => `/projects/${projectId}/permissions`,
```

`entities/permission/api/fetchers.ts`:
```ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";

export async function fetchProjectPermissions(projectId: string): Promise<string[]> {
  const data = await apiFetch<{ projectId: string; permissions: string[] }>(
    API_CONFIG.ENDPOINTS.PROJECTS.PERMISSIONS(projectId),
  );
  return data.permissions;
}
```

`entities/permission/api/query-keys.ts`:
```ts
export const projectPermissionsKeys = {
  all: ["permissions", "project"] as const,
  forProject: (projectId: string) => [...projectPermissionsKeys.all, projectId] as const,
};
```

`entities/permission/hooks/use-project-permissions.ts`:
```ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchProjectPermissions } from "../api/fetchers";
import { projectPermissionsKeys } from "../api/query-keys";

/** Plain useQuery, NOT Suspense — ProjectPermissionProvider needs a
 * non-suspending pending state to implement its global-set fallback (D8). */
export function useProjectPermissionsQuery(projectId: string) {
  return useQuery({
    queryKey: projectPermissionsKeys.forProject(projectId),
    queryFn: () => fetchProjectPermissions(projectId),
    staleTime: 10_000,
  });
}
```

`entities/permission/model/project-permission-context.tsx`:
```tsx
"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useProjectPermissionsQuery } from "../hooks/use-project-permissions";
import { useCan } from "./permission-context";
import type { Permission } from "../lib/permission";

interface ProjectPermissionContextValue {
  can: (resource: string, action: string) => boolean;
}

const ProjectPermissionContext = createContext<ProjectPermissionContextValue | null>(null);

/**
 * Seeds the project-scoped permission set for CanInProject/useCanInProject
 * inside one project's UI tree. D8: while the query is pending or on
 * error, falls back to the outer GLOBAL useCan — the effective set is
 * always a superset of global, so this can only ever under-grant during
 * the fallback window, never over-grant, never flicker a control off.
 */
export function ProjectPermissionProvider({
  projectId,
  children,
}: {
  projectId: string;
  children: ReactNode;
}) {
  const { data, isPending, isError } = useProjectPermissionsQuery(projectId);
  const globalCan = useGlobalCanFallback();

  const permissionSet = useMemo(() => new Set(data ?? []), [data]);
  const can = useCallback(
    (resource: string, action: string) => {
      if (isPending || isError) return globalCan(resource, action);
      return permissionSet.has(`${resource}.${action}`);
    },
    [isPending, isError, globalCan, permissionSet],
  );
  const value = useMemo(() => ({ can }), [can]);

  return <ProjectPermissionContext.Provider value={value}>{children}</ProjectPermissionContext.Provider>;
}

/** Reads the existing global permission context directly, without going
 * through useCan's per-call resource/action signature — needed because
 * the fallback must be reusable for an arbitrary (resource, action) pair
 * computed at call time, not one fixed pair per hook call. */
function useGlobalCanFallback(): (resource: string, action: string) => boolean {
  // useCan itself is (resource, action) => boolean already bound to one
  // pair per call; project-permission-context needs a *function* usable
  // for any pair, so it re-implements the same Set.has check against the
  // sibling global PermissionContext instead of calling useCan directly.
  // Simplest correct approach: call useCan with placeholder args is wrong
  // (useCan is a hook per (resource,action), not reusable as a closure) —
  // so this imports the global context's `can` function directly.
  return useContext(GlobalCanContext);
}

// Re-exported thin accessor so this file doesn't need to know
// PermissionContext's internal shape — see permission-context.tsx for
// the actual GlobalCanContext export added alongside PermissionProvider.
import { GlobalCanContext } from "./permission-context";

export function useCanInProject(resource: string, action: string): boolean {
  const ctx = useContext(ProjectPermissionContext);
  if (ctx === null) throw new Error("useCanInProject must be used within a ProjectPermissionProvider");
  return ctx.can(resource, action);
}
```

This requires exporting the global `can` function (not just `useCan`) from `permission-context.tsx` so the project-scoped fallback can call it directly. Add to `permission-context.tsx` (minimal, additive — every existing export stays):
```ts
export const GlobalCanContext = createContext<(resource: string, action: string) => boolean>(() => false);
```
and in `PermissionProvider`'s return, wrap with an additional provider carrying just the `can` function:
```tsx
  return (
    <PermissionContext.Provider value={value}>
      <GlobalCanContext.Provider value={can}>{children}</GlobalCanContext.Provider>
    </PermissionContext.Provider>
  );
```
(Two nested providers seeded from the same `value`/`can` — no behavior change to any existing `useCan`/`<Can>` call site, purely additive.)

`entities/permission/ui/can-in-project.tsx` (byte-for-byte mirror of `can.tsx`'s two-pass mount guard — read `can.tsx` in full before writing this to copy its exact mounted-state pattern, since the plan text above doesn't reproduce it verbatim):
```tsx
"use client";

import type { ReactNode } from "react";
import { useCanInProject } from "../model/project-permission-context";

interface CanInProjectProps {
  I: string;
  a: string;
  children: ReactNode | ((state: { isAllowed: boolean }) => ReactNode);
  fallback?: ReactNode;
}

export function CanInProject({ I: action, a: resource, children, fallback = null }: CanInProjectProps) {
  const isAllowed = useCanInProject(resource, action);
  if (typeof children === "function") return <>{children({ isAllowed })}</>;
  return <>{isAllowed ? children : fallback}</>;
}
```
(If `can.tsx`'s real current implementation has a mount-guard `useState`/`useEffect` pair for hydration-mismatch avoidance that this plan's earlier research summary mentioned but didn't reproduce verbatim, copy that exact pattern here too — re-read `can.tsx` at implementation time and match it precisely rather than trusting this simplified reconstruction.)

`entities/permission/index.ts` — add exports: `ProjectPermissionProvider`, `useCanInProject`, `CanInProject`, `fetchProjectPermissions`, `projectPermissionsKeys`, `useProjectPermissionsQuery`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/entities/permission/`
Expected: PASS, including every pre-existing test in this directory (e.g. `can.test.tsx` if one exists) unmodified.

- [ ] **Step 5: Typecheck and commit**

```bash
cd frontend && npx tsc --noEmit
git add src/entities/permission/ src/shared/constants/api.ts
git commit -m "feat(permission): add CanInProject/useCanInProject project-scoped primitive (D7+D8)"
```

---

## Task 10: Frontend — project-role CRUD UI + member-role assignment

**Files:**
- Modify: `frontend/src/modules/projects/api/fetchers.ts`
- Modify: `frontend/src/modules/projects/api/query-keys.ts`
- Modify: `frontend/src/shared/constants/permissions.ts`
- Modify: `frontend/src/shared/constants/api.ts`
- Create: `frontend/src/modules/projects/hooks/use-create-project-role.ts`
- Create: `frontend/src/modules/projects/hooks/use-update-project-role.ts`
- Create: `frontend/src/modules/projects/hooks/use-delete-project-role.ts`
- Create: `frontend/src/modules/projects/hooks/use-assign-member-project-role.ts`
- Create: `frontend/src/modules/projects/ui/project-role-form-dialog.tsx`
- Create: `frontend/src/modules/projects/ui/project-roles-section.tsx`
- Modify: `frontend/src/modules/projects/ui/project-detail-view.tsx`
- Modify: `frontend/src/modules/projects/ui/project-member-form-dialog.tsx`
- Modify: `frontend/locales/{en,vi}/modules/{projects,roles}.json`

**Interfaces:**
- Consumes: `ProjectPermissionProvider`/`CanInProject` (Task 9); existing `use-add-project-member.ts`'s mutation-hook shape as the pattern to mirror.
- Produces: `ProjectRole` interface + `fetchProjectRoles`/`createProjectRole`/`updateProjectRole`/`deleteProjectRole`/`assignMemberProjectRole`/`fetchAssignablePermissions`; `projectRolesKeys`; 4 mutation hooks; `<ProjectRoleFormDialog>`, `<ProjectRolesSection>`.

- [ ] **Step 1: `shared/constants/permissions.ts` and `api.ts` additions**

`permissions.ts`: add `PROJECT_ROLE: "project_role"` to `RESOURCES`, and a `PROJECT_ROLE: { RESOURCE, READ: "project_role.read", MANAGE: "project_role.manage" }` block to `PERMISSIONS`, mirroring the existing `CLOUDFLARE_ACCOUNT`-style entries exactly (read the current file's shape before writing this — the plan text elsewhere confirms `RESOURCES`/`ACTIONS`/`PERMISSIONS` already exist with this pattern).

`api.ts`, inside `ENDPOINTS.PROJECTS`, add:
```ts
      ROLES: (projectId: string) => `/projects/${projectId}/roles`,
      ROLE_DETAIL: (id: string) => `/project-roles/${id}`,
      MEMBER_ROLE: (projectId: string, userId: string) => `/projects/${projectId}/members/${userId}/role`,
      ASSIGNABLE_PERMISSIONS: () => `/projects/assignable-permissions`,
```
(Verify against the actual backend route path — Task 8 doesn't define a standalone `/projects/assignable-permissions` route; `ListAssignablePermissions` has no route wired to it in Task 8's list. Add `GET /projects/assignable-permissions` — global, no `project_id`, gated by `require_permission(PROJECT_ROLE, READ)` alone — as a small addendum to Task 8's router changes before starting this task, since the project-role form dialog in this task needs it. Mirror the shape of `list_project_roles`'s router wiring exactly, minus the project-scoping.)

- [ ] **Step 2: `modules/projects/api/fetchers.ts` additions**

```ts
export interface ProjectRolePermissionItem {
  id: string;
  resource: string;
  action: string;
}

export interface ProjectRole {
  id: string;
  projectId: string;
  name: string;
  permissions: ProjectRolePermissionItem[];
}

export async function fetchProjectRoles(projectId: string): Promise<ProjectRole[]> {
  return apiFetch<ProjectRole[]>(API_CONFIG.ENDPOINTS.PROJECTS.ROLES(projectId));
}

export async function fetchAssignablePermissions(): Promise<ProjectRolePermissionItem[]> {
  return apiFetch<ProjectRolePermissionItem[]>(API_CONFIG.ENDPOINTS.PROJECTS.ASSIGNABLE_PERMISSIONS());
}

export async function createProjectRole(
  projectId: string,
  data: { name: string; permissionIds: string[] },
): Promise<ProjectRole> {
  return apiFetch<ProjectRole>(API_CONFIG.ENDPOINTS.PROJECTS.ROLES(projectId), { method: "POST", data });
}

export async function updateProjectRole(
  id: string,
  data: { name?: string; permissionIds?: string[] },
): Promise<ProjectRole> {
  return apiFetch<ProjectRole>(API_CONFIG.ENDPOINTS.PROJECTS.ROLE_DETAIL(id), { method: "PATCH", data });
}

export async function deleteProjectRole(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.ROLE_DETAIL(id), { method: "DELETE" });
}

export async function assignMemberProjectRole(
  projectId: string,
  userId: string,
  projectRoleId: string | null,
): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.PROJECTS.MEMBER_ROLE(projectId, userId), {
    method: "PUT",
    data: { projectRoleId },
  });
}
```
Also extend the existing `ProjectMember` interface with `projectRoleId?: string | null` and `projectRoleName?: string | null`.

`api/query-keys.ts`:
```ts
export const projectRolesKeys = {
  all: ["projects", "roles"] as const,
  forProject: (projectId: string) => [...projectRolesKeys.all, projectId] as const,
};
export const assignablePermissionsKeys = {
  all: ["projects", "assignable-permissions"] as const,
};
```

- [ ] **Step 3: Mutation hooks (mirror `use-add-project-member.ts` exactly)**

```ts
// use-create-project-role.ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProjectRole } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useCreateProjectRole(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: (data: { name: string; permissionIds: string[] }) => createProjectRole(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectRolesKeys.forProject(projectId) });
      success("projectRoleCreated");
    },
    onError: error,
  });
}
```
`use-update-project-role.ts` / `use-delete-project-role.ts` — identical shape, swapping the fetcher and the success message key (`projectRoleUpdated`/`projectRoleDeleted`).

`use-assign-member-project-role.ts` — same shape, but invalidates **two** query keys on success (the member list AND the caller's own effective permission set, since assigning a role changes what THAT member can do):
```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { assignMemberProjectRole } from "../api/fetchers";
import { projectMembersKeys } from "../api/query-keys";
import { projectPermissionsKeys } from "@/entities/permission";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useAssignMemberProjectRole(projectId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("projects");

  return useMutation({
    mutationFn: ({ userId, projectRoleId }: { userId: string; projectRoleId: string | null }) =>
      assignMemberProjectRole(projectId, userId, projectRoleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectMembersKeys.forProject(projectId) });
      queryClient.invalidateQueries({ queryKey: projectPermissionsKeys.forProject(projectId) });
      success("memberRoleAssigned");
    },
    onError: error,
  });
}
```

- [ ] **Step 4: `project-role-form-dialog.tsx` and `project-roles-section.tsx`**

`project-role-form-dialog.tsx` — copy `environment-form-dialog.tsx`'s dialog shell shape exactly (its `Dialog`/`DialogErrorAlert`/form-with-Label-Input pattern, already read in full during Task-9-adjacent research), replacing the type `<select>` with a permission checkbox grid fed by `useQuery({queryKey: assignablePermissionsKeys.all, queryFn: fetchAssignablePermissions})`, and the environment-name `<Input>` with a role-name `<Input>`. Copy `modules/roles/ui/role-form-dialog.tsx`'s checkbox-grid JSX structure specifically for the permissions picker (read that file in full before writing this step for real — it already solves "render a list of checkboxes for a list of permissions, track selected ids in state, submit the array").

`project-roles-section.tsx`:
```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, ShieldCheck } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { fetchProjectRoles, type ProjectRole } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { useDeleteProjectRole } from "../hooks/use-delete-project-role";
import { ProjectRoleFormDialog } from "./project-role-form-dialog";

export function ProjectRolesSection({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const { data: roles = [] } = useQuery({
    queryKey: projectRolesKeys.forProject(projectId),
    queryFn: () => fetchProjectRoles(projectId),
  });
  const deleteRole = useDeleteProjectRole(projectId);
  const [formTarget, setFormTarget] = useState<ProjectRole | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProjectRole | null>(null);

  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
          <ShieldCheck className="size-4" /> {t("sections.projectRoles")}
        </h2>
        <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_ROLE}>
          <Button size="sm" onClick={() => setFormTarget("create")}>
            <Plus className="mr-1.5 size-3.5" /> {t("actions.addProjectRole")}
          </Button>
        </CanInProject>
      </div>
      <div className="flex flex-col divide-y">
        {roles.length === 0 && <p className="text-sm text-muted-foreground">{t("empty.projectRoles")}</p>}
        {roles.map((role) => (
          <div key={role.id} className="flex items-center justify-between py-2 text-sm">
            <span className="font-medium text-foreground">{role.name}</span>
            <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_ROLE}>
              <div className="flex gap-2">
                <button type="button" onClick={() => setFormTarget(role)} className="cursor-pointer text-muted-foreground hover:text-foreground">
                  <Pencil className="size-3.5" />
                </button>
                <button type="button" onClick={() => setDeleteTarget(role)} className="cursor-pointer text-muted-foreground hover:text-destructive">
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </CanInProject>
          </div>
        ))}
      </div>

      {formTarget !== null && (
        <ProjectRoleFormDialog
          isOpen
          onClose={() => setFormTarget(null)}
          projectId={projectId}
          role={formTarget === "create" ? null : formTarget}
        />
      )}
      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteRole.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
        }}
        title={t("deleteConfirm.projectRoleTitle")}
        description={t("deleteConfirm.projectRoleDescription", { name: deleteTarget?.name ?? "" })}
        isLoading={deleteRole.isPending}
      />
    </section>
  );
}
```

- [ ] **Step 5: Wire into `project-detail-view.tsx`**

Wrap the component's returned tree in `<ProjectPermissionProvider projectId={projectId}>...</ProjectPermissionProvider>` (import from `@/entities/permission`). Swap `<Can>` → `<CanInProject>` at the environments/links/members call sites (the ones gating `RESOURCES.ENVIRONMENT`/`PROJECT_LINK`/`PROJECT_MEMBER` actions) — leave every other `<Can>` (Cloudflare/Loki/alert-rule gates) untouched, since those resources are outside `ASSIGNABLE` and would evaluate identically either way; changing them would make the diff misrepresent what actually changed. Mount `<ProjectRolesSection projectId={projectId} />` as a new section. In the Members section, add a role badge (`member.projectRoleName ?? t("members.noRole")`) and, gated by `<CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_MEMBER}>`, a `<select>` calling `useAssignMemberProjectRole(projectId)` with options built from the already-fetched `roles` list (fetch via the same `projectRolesKeys.forProject(projectId)` query already used by `ProjectRolesSection`, reusing TanStack Query's cache rather than a second independent fetch).

`project-member-form-dialog.tsx`: add an optional project-role `<select>` to the add-member form (options from `fetchProjectRoles(projectId)` only — a role from a different project can structurally never appear, since the fetch is already scoped to `projectId`).

- [ ] **Step 6: i18n**

Add to `locales/{en,vi}/modules/projects.json`: `sections.projectRoles`, `actions.addProjectRole`, `empty.projectRoles`, `deleteConfirm.projectRoleTitle`/`projectRoleDescription`, `members.noRole`, `messages.projectRoleCreated`/`projectRoleUpdated`/`projectRoleDeleted`/`memberRoleAssigned`, `errors.projects_project_role_not_found`/`projects_duplicate_project_role_name`/`projects_permission_not_project_assignable`/`projects_project_permission_denied`. Add to `locales/{en,vi}/modules/roles.json`'s `catalog.permissions`: a `project_role: { read: "...", manage: "..." }` block, mirroring the existing `cloudflare_manager`-style entries.

- [ ] **Step 7: Run full frontend gate**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/modules/projects/ src/shared/constants/ locales/
git commit -m "feat(projects): project-role management UI + member-role assignment"
```

---

## Task 11: Whole-feature verification + `reviewing-code-against-skills` pass

**Files:** none (verification only).

- [ ] **Step 1:** `cd backend && ruff check . && ruff format --check . && python scripts/check_module_boundaries.py --strict && uv run lint-imports && uv run mypy app/modules/projects/ app/modules/rbac/ && uv run pytest -q`
- [ ] **Step 2:** `cd frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build`
- [ ] **Step 3:** Manual verification against `itsm_test` (never the live `itsm` database) walking through Task 8's decisive `TestProjectRoleUnionGrant` scenario by hand through the actual UI once the frontend is wired.
- [ ] **Step 4:** Re-seed: `DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run python -m app.seeds.seed_rbac`.
- [ ] **Step 5:** Run the `reviewing-code-against-skills` skill against the full diff (`fastapi-modular-scaffold` for backend, `nextjs-modular-architecture` for frontend) before opening a PR — matches this repo's own established convention for every feature this size.
- [ ] **Step 6:** Follow `finishing-a-development-branch` — branch `feature/project-scoped-permissions` off `develop` (never a direct commit — Hard Rule #8), present the standard 3-option menu, wait for explicit choice.

---

## Self-Review (performed while writing this plan, per the skill's own requirement)

**Spec coverage:** D1 (Task 1, 6), D2 (Task 1, 7, 8), D3 (Task 8's route table — `POST/GET /projects` untouched), D4 (Task 8), D5 (confirmed already shipped — Task 8's route table uses the real, already-existing `PROJECT_LINK`/`PROJECT_MEMBER` resources directly, no re-introduction needed), D6 (Task 2's FK-by-table-name, Task 4's facade methods), D7 (Task 9), D8 (Task 9). Migration/rollout safety point 3(a) — the error-code change — is the literal assertion in Task 8's `TestProjectRoleUnionGrant`. Point 3(b) from the original spec (existing `project:update` holders not gaining `project_link:manage`) is **moot** for this plan since D5 already shipped independently, before this plan was written — not this plan's concern to re-verify or re-disclose.

**Placeholder scan:** no TBD/TODO; every step has real code or an explicit "verify X before writing Y" instruction pointing at a specific file to check, never a vague "add validation."

**Type consistency:** `ProjectPermissionGrant` (Task 6) is consumed identically in Task 8's `require_project_permission*` factories and router bindings (`grant.user.id`/`grant.user.email`). `ProjectRoleRow`/`ProjectRoleRead` field names (`permission_ids` on the raw row vs. `permissions: list[PermissionRead]` on the enriched read model) stay consistently distinct across Tasks 5, 6, 7 — the raw-vs-enriched split mirrors the existing `ProjectMemberRow`/`ProjectMemberRead` and `CloudflareAccountManagerRow`/`Read` precedent exactly, not an inconsistency.

**One known gap surfaced honestly, not hidden:** Task 10 Step 1 discovers mid-plan that `ASSIGNABLE_PERMISSIONS` needs a real backend route Task 8 didn't originally define, and instructs adding it as a small addendum to Task 8 before starting Task 10 — flagged explicitly rather than silently assumed to exist.
