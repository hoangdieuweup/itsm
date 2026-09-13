# Environment-Scoped Cloudflare/Loki/Alerting Access via Project Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Project Role grant environment-scoped, operational Cloudflare (DNS, Tunnel, hostnames, config-read, audit-log-read), Loki, and Alert Rule/Incident permissions — without requiring the grantee to also be a `cloudflare_account_managers` row for the underlying Cloudflare account. Cloudflare account administration (create/delete account, managers, reveal-account-token) and the account↔environment binding itself stay untouched — permanently excluded, same as `project.delete`/`project_role.*` in the original Project Roles plan.

**Architecture:** Extends the already-shipped Project Roles feature (`docs/superpowers/plans/2026-08-25-project-scoped-permissions.md`) rather than building a new mechanism. Adds one new `ProjectsApi` facade method other modules can call to resolve a caller's effective project-scoped permission set. Cloudflare's environment-scoped routes get a single composed dependency that tries the existing account-manager check first (zero behavior change for existing users) and falls back to the project-scoped grant only on failure. Observability's Loki/alert-rule/incident routes — which have no existing Layer-2 ACL at all — get simple new project-scoped dependencies, including two new id-keyed variants (alert_rule_id, incident_id) for routes with no environment_id in their path.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest + testcontainers Postgres (backend only — this plan has no frontend code changes, see Task 10).

**Spec:** This document IS the spec — written directly from two Explore-agent research passes over the actual current code plus a multi-turn clarification with the project owner (Vietnamese). No separate spec doc exists upstream of this plan. The original Project Roles plan (`docs/superpowers/plans/2026-08-25-project-scoped-permissions.md`) is the pattern being extended — read its D1-D9 for context on `resolve_project_permissions`/`ProjectScopedPermissionCatalog`/`ProjectRoleRules.effective_permissions`, all already shipped and merged to `develop`.

## Global Constraints

- **Scope boundary (D1), non-negotiable:** Cloudflare account administration (`cloudflare_account.*`, `cloudflare_manager.*`) and the account↔environment binding itself (`cloudflare_config.manage` — `POST/PATCH/DELETE` on `/cloudflare-configs`) are PERMANENTLY excluded from what a project role may ever grant. Only environment-scoped *operational* atoms become project-role-assignable: `cloudflare_config.read`, all of `cloudflare_dns.*`, all of `cloudflare_tunnel.*`, all of `cloudflare_hostname.*`, `cloudflare_audit.read`, `loki_config.*`, `alert_rule.*`, `incident.*`.
- **D2, disclosed relaxation, stated explicitly not hidden:** the bypass triggers on the caller's EFFECTIVE project-scoped permission grant (global ∪ project-role union) — not narrowed to project-role-sourced-only. A user who already holds a bare global `cloudflare_dns.update` permission AND is a project member (but NOT a `cloudflare_account_managers` row) will, after this change, be able to edit DNS records on environments their project is bound to. This mirrors exactly how `require_project_permission_for_environment` already treats every one of its callers today (no source-distinction exists anywhere in the shipped Project Roles feature) — introducing one here would be new, asymmetric complexity nowhere else in this codebase has.
- **D3, cloudflare composition is OR, never a replacement of the existing check.** The existing account-manager path is tried FIRST — a user who already passes today's check gets the exact same code path, same exception type on failure, and (for the success case) the exact same query shape as today. The project-role path is a pure fallback, only reached on `InsufficientAccountAccess`.
- **No new RBAC catalog rows.** Every atom this plan needs (`cloudflare_config.read`, `cloudflare_dns.*`, `cloudflare_tunnel.*`, `cloudflare_hostname.*`, `cloudflare_audit.read`, `loki_config.*`, `alert_rule.*`, `incident.*`) already exists in `RbacPermissionCatalog.CATALOG` (confirmed by direct query against the running code this session: 65/65 present, zero missing). This plan only adds EXISTING atoms to `ProjectScopedPermissionCatalog.ASSIGNABLE` — never touches `rbac/constants.py`.
- **`.importlinter` already permits this.** `projects-facade`'s `source_modules` already lists `app.modules.cloudflare` and `app.modules.observability` (confirmed by direct read this session) — no `.importlinter` change needed anywhere in this plan.
- **Standing constraint, extra caution this time:** all manual/smoke verification targets the `itsm_test` sibling database on the shared Postgres server at `localhost:5435` — **never** the live `itsm` database. This session already had one incident this exact conversation of running a script against `itsm` (on the `business-chatbot-postgres` container) by mistake after a miscommunication about which database was "safe" — treat any database action outside the automated test suite as requiring an explicit, re-confirmed target before running.
- **No frontend code changes.** The project-role editor's checkbox grid (`frontend/src/modules/projects/ui/project-role-form-dialog.tsx`) already renders whatever `GET /projects/assignable-permissions` returns, grouped generically by `perm.resource` — it needs zero changes to pick up the new catalog entries from Task 1. Task 10 confirms this rather than assuming it.

---

## Task 1: Add environment-scoped Cloudflare/Loki/Alerting atoms to `ProjectScopedPermissionCatalog.ASSIGNABLE`

**Files:**
- Modify: `backend/app/modules/projects/constants.py:81-102`
- Test: `backend/tests/projects/test_rules.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ProjectScopedPermissionCatalog.ASSIGNABLE` grows from 9 to 35 tuples. Every later task in this plan (and the frontend checkbox grid, unchanged) reads this set transitively via `ProjectRoleRules.assignable_keys()`/`.rejects_unassignable(...)`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/projects/test_rules.py`, inside `class TestAssignableKeys`:

```python
    def test_includes_environment_scoped_cloudflare_loki_alerting_atoms(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("cloudflare_dns", "create") in keys
        assert ("cloudflare_tunnel", "create") in keys
        assert ("cloudflare_tunnel", "reveal_token") in keys
        assert ("cloudflare_hostname", "update") in keys
        assert ("cloudflare_config", "read") in keys
        assert ("cloudflare_audit", "read") in keys
        assert ("loki_config", "manage") in keys
        assert ("alert_rule", "create") in keys
        assert ("incident", "acknowledge") in keys

    def test_excludes_cloudflare_account_administration_and_binding(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("cloudflare_account", "create") not in keys
        assert ("cloudflare_account", "delete") not in keys
        assert ("cloudflare_account", "reveal_token") not in keys
        assert ("cloudflare_account", "manage_all") not in keys
        assert ("cloudflare_manager", "read") not in keys
        assert ("cloudflare_manager", "manage") not in keys
        assert ("cloudflare_config", "manage") not in keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/projects/test_rules.py -k "cloudflare_loki_alerting or excludes_cloudflare_account" -v`
Expected: FAIL — `test_includes_environment_scoped_cloudflare_loki_alerting_atoms` fails because none of these tuples are in `ASSIGNABLE` yet; `test_excludes_cloudflare_account_administration_and_binding` trivially passes already (nothing to exclude yet since nothing cloudflare-related is in the set) — confirm it passes for the right reason (there's nothing there yet), not a false positive.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/modules/projects/constants.py`, replace the `ProjectScopedPermissionCatalog` class:

```python
class ProjectScopedPermissionCatalog:
    """The subset of the global rbac.Permission catalog a ProjectRole may
    ever grant. Bounded deliberately: project.delete (cascades every
    downstream Cloudflare/Loki/alerting row), project.manage_all,
    project_member.manage, both project_role.* atoms, all Cloudflare
    ACCOUNT-administration atoms (cloudflare_account.*, cloudflare_manager.*),
    and cloudflare_config.manage (binding/unbinding an environment to an
    account is a trust-establishing action, same class as account
    administration — someone binding an environment already had real
    Cloudflare account access at that moment; a project role must never be
    able to grant that trust itself, only OPERATE within a binding someone
    else already established) are permanently excluded — closing the
    mint-yourself-more-power loop a naive union would open.

    Environment-scoped OPERATIONAL Cloudflare/Loki/Alerting atoms ARE
    assignable: viewing/editing DNS records, creating/deleting/syncing
    Tunnels and their hostnames, revealing a TUNNEL's own connector token
    (narrow blast radius — not the account's api_token), reading the
    account/zone binding and audit logs, configuring Loki, and managing
    alert rules/incidents. See docs/superpowers/plans/2026-08-25-
    environment-scoped-cloudflare-loki-alerting-project-roles.md."""

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
            ("cloudflare_config", "read"),
            ("cloudflare_dns", "read"),
            ("cloudflare_dns", "create"),
            ("cloudflare_dns", "update"),
            ("cloudflare_dns", "delete"),
            ("cloudflare_tunnel", "read"),
            ("cloudflare_tunnel", "create"),
            ("cloudflare_tunnel", "delete"),
            ("cloudflare_tunnel", "sync"),
            ("cloudflare_tunnel", "reveal_token"),
            ("cloudflare_tunnel", "refresh_status"),
            ("cloudflare_hostname", "read"),
            ("cloudflare_hostname", "create"),
            ("cloudflare_hostname", "update"),
            ("cloudflare_hostname", "delete"),
            ("cloudflare_audit", "read"),
            ("loki_config", "read"),
            ("loki_config", "manage"),
            ("alert_rule", "create"),
            ("alert_rule", "read"),
            ("alert_rule", "update"),
            ("alert_rule", "delete"),
            ("incident", "create"),
            ("incident", "read"),
            ("incident", "acknowledge"),
            ("incident", "resolve"),
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/projects/test_rules.py -v`
Expected: PASS, all tests in the file, including the two new ones and every pre-existing one unmodified (the 9 original tuples are untouched, only additive).

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/modules/projects/constants.py tests/projects/test_rules.py
git commit -m "feat(projects): allow project roles to grant environment-scoped Cloudflare/Loki/Alerting atoms"
```

---

## Task 2: New `ProjectsApi.resolve_effective_permissions` facade method

**Files:**
- Modify: `backend/app/modules/projects/public.py`
- Test: `backend/tests/projects/test_public.py` (create if it doesn't exist — check first)

**Interfaces:**
- Consumes: `app.modules.projects.access.resolve_project_permissions(project_id, user, rbac_api, uow) -> ProjectPermissionGrant` (existing, unchanged, `backend/app/modules/projects/access.py`).
- Produces: `ProjectsApi.resolve_effective_permissions(self, project_id: UUID, user: UserRead, rbac_api: RbacApi) -> frozenset[str]` — the ONLY way cloudflare/observability may reach this logic (cross-module boundary). Tasks 3, 5, 6, 8 all depend on this exact signature.

- [ ] **Step 1: Check whether `backend/tests/projects/test_public.py` already exists**

Run: `ls backend/tests/projects/test_public.py 2>&1`

If it doesn't exist, this step creates it fresh with the header below. If it does exist, read it first and add the test class to the existing file instead of overwriting it.

- [ ] **Step 2: Write the failing test**

```python
"""Unit tests for app.modules.projects.public.ProjectsApi — Fake-based, no database."""

from uuid import uuid4

from app.modules.projects.public import ProjectsApi
from app.modules.users.public import UserRead
from tests.projects.test_services import ACTOR_EMAIL, ACTOR_ID, FakeProjectsUnitOfWork, FakeRbacApi


class TestResolveEffectivePermissions:
    async def test_returns_the_union_of_global_and_project_role_permissions(self) -> None:
        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        await uow.project_members.add(project.id, ACTOR_ID)
        role_perm_id = uuid4()
        role = await uow.project_roles.create(
            project_id=project.id, name="dns-editor", permission_ids=[role_perm_id]
        )
        await uow.project_members.set_project_role(project.id, ACTOR_ID, role.id)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(
            manage_all=False,
            global_permissions=["project.read"],
            catalog_by_id={role_perm_id: "cloudflare_dns.create"},
        )
        api = ProjectsApi(uow)

        permissions = await api.resolve_effective_permissions(project.id, user, rbac_api)

        assert permissions == frozenset({"project.read", "cloudflare_dns.create"})

    async def test_raises_insufficient_project_access_for_a_non_member(self) -> None:
        from app.modules.projects.exceptions import InsufficientProjectAccess
        import pytest

        uow = FakeProjectsUnitOfWork()
        project = await uow.projects.create(name="A", description=None, created_by=None)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=[])
        api = ProjectsApi(uow)

        with pytest.raises(InsufficientProjectAccess):
            await api.resolve_effective_permissions(project.id, user, rbac_api)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/projects/test_public.py -v`
Expected: FAIL — `AttributeError: 'ProjectsApi' object has no attribute 'resolve_effective_permissions'`.

- [ ] **Step 4: Write minimal implementation**

In `backend/app/modules/projects/public.py`, add the import and the method:

```python
from app.modules.projects.access import resolve_project_permissions
```

Add to `class ProjectsApi`, after `get_environment_by_id`:

```python
    @facade
    async def resolve_effective_permissions(
        self, project_id: UUID, user: UserRead, rbac_api: RbacApi
    ) -> frozenset[str]:
        """The caller's effective 'resource.action' set inside project_id —
        their global permissions UNIONed with whatever their assigned
        ProjectRole grants. Raises InsufficientProjectAccess if the caller
        is neither a member of project_id nor holds project:manage_all.
        The single entry point other modules (cloudflare, observability)
        use to extend environment-scoped access via project roles — see
        docs/superpowers/plans/2026-08-25-environment-scoped-cloudflare-
        loki-alerting-project-roles.md."""
        grant = await resolve_project_permissions(project_id, user, rbac_api, self._uow)
        return grant.permissions
```

Add `RbacApi` and `UserRead` to the imports if not already present:

```python
from app.modules.rbac.public import RbacApi
from app.modules.users.public import UserRead
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/projects/test_public.py -v`
Expected: PASS, both tests.

- [ ] **Step 6: Confirm no circular import**

Run: `cd backend && uv run lint-imports && python scripts/check_module_boundaries.py --strict`
Expected: both clean. `projects/public.py` importing `projects/access.py` is an intra-module import (same module, always allowed) — this step is a sanity check, not expected to find anything.

- [ ] **Step 7: Commit**

```bash
git add app/modules/projects/public.py tests/projects/test_public.py
git commit -m "feat(projects): add ProjectsApi.resolve_effective_permissions facade method"
```

---

## Task 3: Cloudflare — composed `require_cloudflare_environment_access` dependency

**Files:**
- Modify: `backend/app/modules/cloudflare/dependencies.py`
- Test: `backend/tests/cloudflare/test_dependencies.py` (create if it doesn't exist — check first, same as Task 2 Step 1)

**Interfaces:**
- Consumes: `resolve_account_access_grant` (existing, `cloudflare/access.py`), `ProjectsApi.get_environment_by_id`/`resolve_effective_permissions` (Task 2), `RbacApi.has_permission(user_id, resource, action) -> bool` (existing, `rbac/public.py`).
- Produces: `require_cloudflare_environment_access(resource: str, action: str, min_level: AccessLevel)` — a dependency factory returning `Depends(...) -> AccountAccessGrant`, the SAME return type every existing `require_account_access_for_environment(min_level)` caller already expects. Task 4 replaces every in-scope route's TWO existing `Depends()` (`require_permission` + `require_account_access_for_environment`) with this ONE.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/cloudflare/test_dependencies.py` (check first whether it exists; if it does, add this class to it):

```python
"""Unit tests for app.modules.cloudflare.dependencies — Fake-based, no database."""

from uuid import uuid4

import pytest

from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.dependencies import require_cloudflare_environment_access
from app.modules.cloudflare.exceptions import InsufficientAccountAccess
from app.modules.users.public import UserRead
from tests.cloudflare.test_services import ACTOR_EMAIL, ACTOR_ID, FakeCloudflareUnitOfWork, FakeRbacApi
from tests.projects.test_services import FakeProjectsUnitOfWork


class FakeProjectsApiForDependencyTest:
    """Minimal stand-in exposing exactly the two ProjectsApi methods this
    dependency calls — not the full Fake used elsewhere, since this test
    only needs to control get_environment_by_id/resolve_effective_permissions
    directly rather than building a whole project graph."""

    def __init__(self, environment=None, permissions: frozenset[str] = frozenset()):
        self._environment = environment
        self._permissions = permissions

    async def get_environment_by_id(self, environment_id):
        return self._environment

    async def resolve_effective_permissions(self, project_id, user, rbac_api):
        return self._permissions


class TestRequireCloudflareEnvironmentAccess:
    async def test_existing_account_manager_path_is_tried_first_and_unchanged(self) -> None:
        """A user who already passes today's check (global permission +
        account-manager row) must succeed via the FIRST branch — this proves
        zero behavior change for existing users, the core promise of D3."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acct", cf_account_id="cf1", api_token_ciphertext=b"x", created_by=ACTOR_ID
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="z.com"
        )
        await uow.account_managers.assign(account.id, ACTOR_ID, AccessLevel.EDITOR)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=["cloudflare_dns.create"])
        projects_api = FakeProjectsApiForDependencyTest()  # never consulted on this path

        check = require_cloudflare_environment_access("cloudflare_dns", "create", AccessLevel.EDITOR)
        grant = await check(
            environment_id=config.environment_id,
            auth_api=_FakeAuthApi(user),
            rbac_api=rbac_api,
            uow=uow,
            projects_api=projects_api,
        )

        assert grant.held_level == AccessLevel.EDITOR

    async def test_falls_back_to_project_role_grant_when_not_an_account_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acct", cf_account_id="cf1", api_token_ciphertext=b"x", created_by=ACTOR_ID
        )
        environment_id = uuid4()
        await uow.configs.create(
            environment_id=environment_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="z.com"
        )
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=[])  # no global permission either
        projects_api = FakeProjectsApiForDependencyTest(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
            permissions=frozenset({"cloudflare_dns.create"}),
        )

        check = require_cloudflare_environment_access("cloudflare_dns", "create", AccessLevel.EDITOR)
        grant = await check(
            environment_id=environment_id,
            auth_api=_FakeAuthApi(user),
            rbac_api=rbac_api,
            uow=uow,
            projects_api=projects_api,
        )

        assert grant.held_level is None  # bypassed via the project-role path, mirrors manage_all's signal

    async def test_raises_insufficient_account_access_when_both_paths_fail(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acct", cf_account_id="cf1", api_token_ciphertext=b"x", created_by=ACTOR_ID
        )
        environment_id = uuid4()
        await uow.configs.create(
            environment_id=environment_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="z.com"
        )
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        rbac_api = FakeRbacApi(manage_all=False, global_permissions=[])
        projects_api = FakeProjectsApiForDependencyTest(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
            permissions=frozenset(),  # project role grants nothing relevant
        )

        check = require_cloudflare_environment_access("cloudflare_dns", "create", AccessLevel.EDITOR)
        with pytest.raises(InsufficientAccountAccess):
            await check(
                environment_id=environment_id,
                auth_api=_FakeAuthApi(user),
                rbac_api=rbac_api,
                uow=uow,
                projects_api=projects_api,
            )


class _FakeAuthApi:
    def __init__(self, user: UserRead) -> None:
        self._user = user

    def current_user(self) -> UserRead:
        return self._user


class _FakeEnvironment:
    def __init__(self, id, project_id) -> None:
        self.id = id
        self.project_id = project_id
```

Note: this test file references `FakeCloudflareUnitOfWork`/`FakeRbacApi`/`ACTOR_ID`/`ACTOR_EMAIL` from `tests/cloudflare/test_services.py` — read that file first (`backend/tests/cloudflare/test_services.py`) to confirm the exact constructor signatures for `FakeCloudflareUnitOfWork().accounts.create(...)`/`.configs.create(...)`/`.account_managers.assign(...)` match what's used above; adjust the test's setup calls to match the REAL fake's actual method signatures if they differ from this sketch (this plan was written from the cloudflare test file's existence, not its full contents — verify before running).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_dependencies.py -v`
Expected: FAIL — `ImportError: cannot import name 'require_cloudflare_environment_access'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/modules/cloudflare/dependencies.py`, add the import:

```python
from app.modules.projects.public import ProjectsApi, get_projects_api
```

Add after `require_account_access_for_environment`:

```python
def require_cloudflare_environment_access(resource: str, action: str, min_level: AccessLevel):
    """Composed check for environment-scoped Cloudflare routes (DNS, Tunnel,
    hostnames, config-read, audit-log-read) — never used on account
    administration or binding/unbinding routes, which stay exclusively
    gated by require_account_access*/require_account_access_for_environment.

    Tries the EXISTING account-manager path first: global resource.action
    permission AND sufficient cloudflare_account_managers level (or
    cloudflare_account:manage_all) — byte-for-byte today's combined
    Layer-1+Layer-2 behavior, same queries, same success shape, for every
    user who already passes it. Only on failure does it fall back to the
    caller's project-scoped effective permission grant (global UNION
    project role) for the environment's project — additive, never a
    narrowing of what account-manager-based access already allows. Both
    paths failing always raises InsufficientAccountAccess, so the error
    code a caller sees never depends on which branch was tried.

    held_level=None on the returned grant signals 'bypassed via a
    mechanism other than a literal cloudflare_account_managers row' —
    the exact same signal cloudflare_account:manage_all already uses,
    so any code inspecting held_level treats this identically to a
    manage_all bypass (deliberate: neither carries a real per-account
    tier, both should satisfy any level check downstream)."""

    async def check(
        environment_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
        projects_api: ProjectsApi = Depends(get_projects_api),
    ) -> AccountAccessGrant:
        user = auth_api.current_user()
        config = await uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()

        if await rbac_api.has_permission(user.id, resource, action):
            try:
                return await resolve_account_access_grant(
                    config.cloudflare_account_id, user, rbac_api, uow, min_level
                )
            except InsufficientAccountAccess:
                pass

        environment = await projects_api.get_environment_by_id(environment_id)
        if environment is not None:
            permissions = await projects_api.resolve_effective_permissions(
                environment.project_id, user, rbac_api
            )
            if f"{resource}.{action}" in permissions:
                return AccountAccessGrant(user=user, held_level=None)

        raise InsufficientAccountAccess()

    return check
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_dependencies.py -v`
Expected: PASS, all three tests.

- [ ] **Step 5: Confirm no circular import / boundary violation**

Run: `cd backend && uv run lint-imports && python scripts/check_module_boundaries.py --strict`
Expected: both clean — `cloudflare/dependencies.py` importing `app.modules.projects.public` is exactly the sanctioned cross-module path (`projects-facade` already lists `app.modules.cloudflare` in `source_modules`, confirmed this session).

- [ ] **Step 6: Commit**

```bash
git add app/modules/cloudflare/dependencies.py tests/cloudflare/test_dependencies.py
git commit -m "feat(cloudflare): add require_cloudflare_environment_access — project-role fallback for environment-scoped routes"
```

---

## Task 4: Migrate cloudflare's in-scope routes to the composed dependency

**Files:**
- Modify: `backend/app/modules/cloudflare/router.py`
- Test: `backend/tests/cloudflare/test_router.py` (extend existing tests, don't rewrite)

**Interfaces:**
- Consumes: `require_cloudflare_environment_access(resource, action, min_level)` (Task 3).
- Produces: every in-scope route now takes ONE `_grant: AccountAccessGrant = Depends(require_cloudflare_environment_access(...))` instead of TWO separate `Depends()` calls. Task 9's decisive test depends on this migration being complete and correct for every route in the table below.

- [ ] **Step 1: Read the current router file in full**

Run: `cd backend && cat -n app/modules/cloudflare/router.py | sed -n '260,565p'`

Confirm the exact current line numbers/import names before editing — this plan's line-number references (from this session's research pass) may have shifted if any other change landed on this file since. Do not assume the table below's line numbers are still accurate; use them as a route-identity guide, not literal line targets.

- [ ] **Step 2: Write the failing tests first — pick 3 representative routes, not all 15**

Add to `backend/tests/cloudflare/test_router.py` (a new test class; read the file's existing `_login_with_permissions`-equivalent helper first and reuse it — cloudflare's router tests were written by an earlier phase this session and already have their own login helper, confirm its exact name/signature before writing these):

```python
class TestProjectRoleGrantsEnvironmentScopedCloudflareAccess:
    async def test_project_role_grants_tunnel_create_without_account_manager_row(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """The decisive proof for D2/D3: a collaborator with ZERO
        cloudflare_account_managers row, but a project role granting
        cloudflare_tunnel.create, succeeds on POST .../cloudflare-tunnels."""
        # Full end-to-end setup (admin creates account+binds environment+
        # creates project role+adds collaborator+assigns role) belongs in
        # Task 9's decisive test — this task's tests only need to prove the
        # DEPENDENCY migration compiles and gates correctly per-route using
        # the same lighter-weight per-route pattern the existing file
        # already uses elsewhere (read 2-3 existing tests in this file
        # for the exact fixture/helper shapes before writing this one).
        ...

    async def test_binding_route_still_requires_account_manager_not_project_role(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """PATCH .../cloudflare-config (binding) is explicitly OUT of scope
        (D1) — a project-role grant of cloudflare_config.read/manage must
        NOT let a non-account-manager rebind the environment."""
        ...

    async def test_account_creation_route_untouched_by_project_roles(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """POST /cloudflare-accounts (account administration) is untouched
        — a project role can never satisfy this route's require_permission
        (cloudflare_account, create) check, since cloudflare_account.* was
        never added to ASSIGNABLE (Task 1)."""
        ...
```

These three bodies are intentionally sketched, not filled in yet — the executor's actual Step 2 work is: (a) read `backend/tests/cloudflare/test_router.py` in full to learn its exact `_login_with_permissions`/client-setup helper, (b) fill in each `...` with real, complete test code using that helper, matching the shape of the 3-4 nearest existing tests in the same file, (c) then proceed to Step 3 below. Do not run these as-is; complete them first. This is the one legitimate exception to "no placeholders" in this plan — the exact login-helper shape genuinely cannot be hardcoded here without having freshly re-read a file that may have changed, and instructing the executor to read-then-fill is itself a complete, actionable instruction, not a vague one.

- [ ] **Step 3: Run the (now-completed) tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_router.py -k "ProjectRoleGrantsEnvironmentScopedCloudflareAccess" -v`
Expected: the tunnel-create test fails (403, since the migration hasn't happened yet); the other two currently pass already (nothing has changed yet) — confirm they pass for the right reason.

- [ ] **Step 4: Migrate every in-scope route**

For each route below, in `backend/app/modules/cloudflare/router.py`, replace the TWO existing `Depends()` params with ONE. Pattern shown once in full for the first route; apply identically for the rest (only the resource/action/level string arguments change — copy this exact transformation for every remaining route in the list):

**Before** (`GET /environments/{environment_id}/cloudflare-config`):
```python
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_CONFIG, RbacActions.READ)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
```

**After:**
```python
    _grant: AccountAccessGrant = Depends(
        require_cloudflare_environment_access(RbacResources.CLOUDFLARE_CONFIG, RbacActions.READ, AccessLevel.VIEWER)
    ),
```

Apply this identical transformation (delete the `_l1`/Layer-1 param, replace the Layer-2 param's `Depends(...)` call) to every one of these 15 routes — **do NOT touch** `POST /cloudflare-configs`, `PATCH /environments/{id}/cloudflare-config`, `DELETE /environments/{id}/cloudflare-config`, `GET /cloudflare-accounts/{id}/zones`, or any `cloudflare_account.*`/`cloudflare_manager.*`/manager-CRUD route — those stay exactly as they are today, per D1/D8:

| Route | resource | action | min_level |
|---|---|---|---|
| `GET /environments/{id}/dns-records` | `CLOUDFLARE_DNS` | `READ` | `VIEWER` |
| `POST /environments/{id}/dns-records/sync` | `CLOUDFLARE_DNS` | `READ` | `VIEWER` |
| `GET /environments/{id}/cloudflare-audit-logs` | `CLOUDFLARE_AUDIT` | `READ` | `VIEWER` |
| `POST /environments/{id}/dns-records` | `CLOUDFLARE_DNS` | `CREATE` | `EDITOR` |
| `PATCH /environments/{id}/dns-records/{record_id}` | `CLOUDFLARE_DNS` | `UPDATE` | `EDITOR` |
| `DELETE /environments/{id}/dns-records/{record_id}` | `CLOUDFLARE_DNS` | `DELETE` | `EDITOR` |
| `GET /environments/{id}/cloudflare-tunnels` | `CLOUDFLARE_TUNNEL` | `READ` | `VIEWER` |
| `POST /environments/{id}/cloudflare-tunnels/sync` | `CLOUDFLARE_TUNNEL` | `SYNC` | `EDITOR` |
| `POST /environments/{id}/cloudflare-tunnels` | `CLOUDFLARE_TUNNEL` | `CREATE` | `EDITOR` |
| `DELETE .../cloudflare-tunnels/{tunnel_id}` | `CLOUDFLARE_TUNNEL` | `DELETE` | `EDITOR` |
| `POST .../{tunnel_id}/reveal-token` | `CLOUDFLARE_TUNNEL` | `REVEAL_TOKEN` | `EDITOR` |
| `POST .../{tunnel_id}/refresh-status` | `CLOUDFLARE_TUNNEL` | `REFRESH_STATUS` | `EDITOR` |
| `GET .../{tunnel_id}/hostnames` | `CLOUDFLARE_HOSTNAME` | `READ` | `VIEWER` |
| `POST .../{tunnel_id}/hostnames` | `CLOUDFLARE_HOSTNAME` | `CREATE` | `EDITOR` |
| `PATCH .../hostnames/{hostname_id}` | `CLOUDFLARE_HOSTNAME` | `UPDATE` | `EDITOR` |
| `DELETE .../hostnames/{hostname_id}` | `CLOUDFLARE_HOSTNAME` | `DELETE` | `EDITOR` |

(16 routes listed — includes `GET /environments/{id}/cloudflare-config` shown as the worked example above, so 15 additional after it, 16 total migrated in this task.)

Also migrate the ONE already-shown route (`GET /environments/{id}/cloudflare-config`) per the worked example.

After every route is migrated, remove any now-unused imports (`require_permission`, `RbacActions`, `UserRead` if no longer referenced elsewhere in the file — check with a grep before deleting, other routes in the same file may still use them for the excluded account-management routes).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_router.py -v`
Expected: PASS — every existing test in the file (proving zero regression for account-manager-based access) plus the 3 new tests from Step 2.

- [ ] **Step 6: Full cloudflare module gate**

Run: `cd backend && ruff check app/modules/cloudflare/ tests/cloudflare/ && ruff format --check app/modules/cloudflare/ tests/cloudflare/ && uv run mypy app/modules/cloudflare/`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add app/modules/cloudflare/router.py tests/cloudflare/test_router.py
git commit -m "feat(cloudflare): migrate 16 environment-scoped routes to require_cloudflare_environment_access"
```

---

## Task 5: Observability — new project-scoped dependency + Loki/environment-keyed alert-rule route migration

**Files:**
- Modify: `backend/app/modules/observability/dependencies.py`
- Modify: `backend/app/modules/observability/exceptions.py`
- Modify: `backend/app/modules/observability/router.py`
- Test: `backend/tests/observability/test_dependencies.py` (create if it doesn't exist)
- Test: `backend/tests/observability/test_router.py` (extend existing)

**Interfaces:**
- Consumes: `ProjectsApi.get_environment_by_id`/`resolve_effective_permissions` (Task 2).
- Produces: `require_project_permission_for_environment(resource: str, action: str)` in `observability/dependencies.py` — a NEW module-local factory (observability cannot import projects' own factory of the same name directly; the cross-module boundary only permits `projects.public`, and `require_project_permission_for_environment` is not exported there — confirmed this session). Returns `Depends(...) -> UserRead`. New `ObservabilityPermissionDenied` exception (observability owns its own errors, mirrors `ProjectPermissionDenied`'s reasoning exactly).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/observability/test_dependencies.py`:

```python
"""Unit tests for app.modules.observability.dependencies — Fake-based, no database."""

from uuid import uuid4

import pytest

from app.modules.observability.dependencies import require_project_permission_for_environment
from app.modules.observability.exceptions import ObservabilityPermissionDenied
from app.modules.users.public import UserRead


class _FakeAuthApi:
    def __init__(self, user: UserRead) -> None:
        self._user = user

    def current_user(self) -> UserRead:
        return self._user


class _FakeEnvironment:
    def __init__(self, id, project_id) -> None:
        self.id = id
        self.project_id = project_id


class _FakeProjectsApi:
    def __init__(self, environment=None, permissions: frozenset[str] = frozenset()):
        self._environment = environment
        self._permissions = permissions

    async def get_environment_by_id(self, environment_id):
        return self._environment

    async def resolve_effective_permissions(self, project_id, user, rbac_api):
        return self._permissions


class TestRequireProjectPermissionForEnvironment:
    async def test_allows_when_resource_action_is_in_the_effective_grant(self) -> None:
        environment_id = uuid4()
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")
        projects_api = _FakeProjectsApi(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
            permissions=frozenset({"loki_config.manage"}),
        )

        check = require_project_permission_for_environment("loki_config", "manage")
        result = await check(
            environment_id=environment_id,
            auth_api=_FakeAuthApi(user),
            rbac_api=object(),
            projects_api=projects_api,
        )

        assert result == user

    async def test_raises_when_resource_action_is_missing(self) -> None:
        environment_id = uuid4()
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")
        projects_api = _FakeProjectsApi(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
            permissions=frozenset(),
        )

        check = require_project_permission_for_environment("loki_config", "manage")
        with pytest.raises(ObservabilityPermissionDenied):
            await check(
                environment_id=environment_id,
                auth_api=_FakeAuthApi(user),
                rbac_api=object(),
                projects_api=projects_api,
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/observability/test_dependencies.py -v`
Expected: FAIL — `ImportError` (neither `require_project_permission_for_environment` nor `ObservabilityPermissionDenied` exist yet).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/modules/observability/exceptions.py`, add:

```python
class ObservabilityPermissionDenied(ForbiddenError):
    """Raised when the caller's effective project permission set (global
    UNION project role) does not include the required resource.action for
    this environment. Observability-owned rather than importing projects'
    ProjectPermissionDenied — that class isn't exported through
    projects/public.py, and cross-module error reuse would break the
    module-owns-its-errors rule (mirrors ProjectPermissionDenied's own
    docstring reasoning in the projects module)."""

    code = ErrorCode.PERMISSION_DENIED
    message = "You do not have this permission on this project"
```

Check `ErrorCode` in `backend/app/modules/observability/constants.py` first — if `PERMISSION_DENIED` doesn't already exist as a member, add it (`PERMISSION_DENIED = "observability_permission_denied"`, following the exact naming convention every other member in that enum already uses — read the enum first to match the prefix style exactly).

In `backend/app/modules/observability/dependencies.py`, add the import:

```python
from app.modules.projects.public import ProjectsApi, get_projects_api
from app.modules.observability.exceptions import ObservabilityEnvironmentNotFound, ObservabilityPermissionDenied
```

Add the new dependency factory (near the top, before the use-case providers):

```python
def require_project_permission_for_environment(resource: str, action: str):
    """Environment-scoped project-permission gate — the observability
    module's own thin wrapper, since require_project_permission_for_
    environment in projects/dependencies.py cannot be imported directly
    (cross-module boundary only permits projects.public, which does not
    export it). Delegates the actual union computation to
    ProjectsApi.resolve_effective_permissions (the one sanctioned path)."""

    async def check(
        environment_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        projects_api: ProjectsApi = Depends(get_projects_api),
    ) -> UserRead:
        user = auth_api.current_user()
        environment = await projects_api.get_environment_by_id(environment_id)
        if environment is None:
            raise ObservabilityEnvironmentNotFound()
        permissions = await projects_api.resolve_effective_permissions(
            environment.project_id, user, rbac_api
        )
        if f"{resource}.{action}" not in permissions:
            raise ObservabilityPermissionDenied()
        return user

    return check
```

Confirm `AuthApi`/`get_auth_api`/`RbacApi`/`get_rbac_api`/`UserRead`/`UUID` are already imported at the top of this file (per the earlier research pass, `get_create_loki_config` and siblings already use `AuditApi`/`ProjectsApi` — check whether `AuthApi`/`RbacApi` specifically are already imported; add them if missing).

In `backend/app/modules/observability/router.py`, migrate these 6 routes from `require_permission(RbacResources.LOKI_CONFIG, RbacActions.X)` to `require_project_permission_for_environment(RbacResources.LOKI_CONFIG, RbacActions.X)` (same resource/action string, just swap which factory builds the dependency — the return type changes from `UserRead` to `UserRead` too, no router body changes needed beyond the `Depends(...)` call itself):

| Route | action |
|---|---|
| `POST /environments/{id}/loki-config` | `MANAGE` |
| `GET /environments/{id}/loki-config` | `READ` |
| `PATCH /environments/{id}/loki-config` | `MANAGE` |
| `DELETE /environments/{id}/loki-config` | `MANAGE` |
| `POST /environments/{id}/loki-config/query` | `READ` |
| `GET /environments/{id}/loki-config/tail` | `READ` |

And these 2 alert-rule routes (environment_id IS in their path):

| Route | action |
|---|---|
| `POST /environments/{id}/alert-rules` | `CREATE` (resource: `ALERT_RULE`) |
| `GET /environments/{id}/alert-rules` | `READ` (resource: `ALERT_RULE`) |

Add the import `from app.modules.observability.dependencies import require_project_permission_for_environment` to `router.py` if not already present (it will already have `require_permission` imported from rbac — leave that import, other routes in this file still need it).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_dependencies.py -v`
Expected: PASS, both tests.

- [ ] **Step 5: Run the full observability router test suite**

Run: `cd backend && uv run pytest tests/observability/test_router.py -v`
Expected: PASS — every existing test (proving the 8 migrated routes behave identically for a global-permission-only user, since project_role_id=NULL means the effective grant is exactly their global set) plus confirm no test needs updating (if any existing test's expected error code was `rbac_permission_denied` for one of these 8 routes, it will now need to become `observability_permission_denied` — find and fix any such test, this IS an expected, disclosed error-code change for these 8 routes specifically, matching the original Project Roles plan's own precedent).

- [ ] **Step 6: Commit**

```bash
git add app/modules/observability/dependencies.py app/modules/observability/exceptions.py app/modules/observability/router.py app/modules/observability/constants.py tests/observability/test_dependencies.py tests/observability/test_router.py
git commit -m "feat(observability): migrate Loki config + environment-keyed alert-rule routes to project-scoped permission"
```

---

## Task 6: Observability — id-keyed dependencies for alert_rule and incident

**Files:**
- Modify: `backend/app/modules/observability/dependencies.py`
- Test: `backend/tests/observability/test_dependencies.py`

**Interfaces:**
- Consumes: `uow.alert_rules.get_by_id(entity_id) -> AlertRuleRead | None` (confirmed existing, `observability/repository.py:255`), `uow.incidents.get_by_id(entity_id) -> IncidentRead | None` (confirmed existing, `observability/repository.py:429`), `ProjectsApi.get_environment_by_id`/`resolve_effective_permissions` (Task 2). `AlertRuleRead.environment_id: UUID` and `IncidentRead.project_id: UUID`/`.environment_id: UUID` (confirmed existing on the `AlertRule`/`Incident` models this session — `Incident` has BOTH columns directly, `AlertRule` has only `environment_id`).
- Produces: `require_project_permission_for_alert_rule(resource, action)` and `require_project_permission_for_incident(resource, action)` — both `Depends(...) -> UserRead`. Task 7 wires these onto 4 routes.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/observability/test_dependencies.py`:

```python
class TestRequireProjectPermissionForAlertRule:
    async def test_resolves_via_the_alert_rules_environment_then_project(self) -> None:
        from app.modules.observability.dependencies import require_project_permission_for_alert_rule
        from tests.observability.test_services import FakeObservabilityUnitOfWork

        uow = FakeObservabilityUnitOfWork()
        environment_id = uuid4()
        alert_rule = await uow.alert_rules.create(
            environment_id=environment_id,
            name="r1",
            source="cloudflare_native",
            severity="high",
            cf_alert_type="advanced_ddos_attack_l7_alert",
            condition=None,
        )
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")
        projects_api = _FakeProjectsApi(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
            permissions=frozenset({"alert_rule.update"}),
        )

        check = require_project_permission_for_alert_rule("alert_rule", "update")
        result = await check(
            alert_rule_id=alert_rule.id,
            auth_api=_FakeAuthApi(user),
            rbac_api=object(),
            uow=uow,
            projects_api=projects_api,
        )

        assert result == user


class TestRequireProjectPermissionForIncident:
    async def test_resolves_via_the_incidents_own_project_id_column(self) -> None:
        from app.modules.observability.dependencies import require_project_permission_for_incident
        from tests.observability.test_services import FakeObservabilityUnitOfWork

        uow = FakeObservabilityUnitOfWork()
        project_id = uuid4()
        incident = await uow.incidents.create(
            project_id=project_id,
            environment_id=uuid4(),
            alert_rule_id=None,
            source="manual",
            category="manual",
            severity="low",
            title="t",
        )
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")
        projects_api = _FakeProjectsApi(permissions=frozenset({"incident.acknowledge"}))

        check = require_project_permission_for_incident("incident", "acknowledge")
        result = await check(
            incident_id=incident.id,
            auth_api=_FakeAuthApi(user),
            rbac_api=object(),
            uow=uow,
            projects_api=projects_api,
        )

        assert result == user
```

Before running, read `backend/tests/observability/test_services.py` in full to confirm `FakeObservabilityUnitOfWork`'s exact `.alert_rules.create(...)`/`.incidents.create(...)` signatures (this plan's sketch above uses plausible field names inferred from the real `AlertRule`/`Incident` models read this session, but the FAKE's constructor may differ slightly — adjust to match, don't guess further than what's written here).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/observability/test_dependencies.py -k "AlertRule or Incident" -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/modules/observability/dependencies.py`:

```python
def require_project_permission_for_alert_rule(resource: str, action: str):
    """Same shape as require_project_permission_for_environment, keyed by
    alert_rule_id — resolves AlertRule.environment_id first (AlertRule has
    no project_id column of its own, only environment_id)."""

    async def check(
        alert_rule_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
        projects_api: ProjectsApi = Depends(get_projects_api),
    ) -> UserRead:
        user = auth_api.current_user()
        alert_rule = await uow.alert_rules.get_by_id(alert_rule_id)
        if alert_rule is None:
            raise AlertRuleNotFound()
        environment = await projects_api.get_environment_by_id(alert_rule.environment_id)
        if environment is None:
            raise AlertRuleNotFound()
        permissions = await projects_api.resolve_effective_permissions(
            environment.project_id, user, rbac_api
        )
        if f"{resource}.{action}" not in permissions:
            raise ObservabilityPermissionDenied()
        return user

    return check


def require_project_permission_for_incident(resource: str, action: str):
    """Same shape, keyed by incident_id — Incident has its OWN project_id
    column directly (unlike AlertRule), so no environment lookup needed."""

    async def check(
        incident_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
        projects_api: ProjectsApi = Depends(get_projects_api),
    ) -> UserRead:
        user = auth_api.current_user()
        incident = await uow.incidents.get_by_id(incident_id)
        if incident is None:
            raise IncidentNotFound()
        permissions = await projects_api.resolve_effective_permissions(
            incident.project_id, user, rbac_api
        )
        if f"{resource}.{action}" not in permissions:
            raise ObservabilityPermissionDenied()
        return user

    return check
```

Confirm `AlertRuleNotFound`/`IncidentNotFound`/`AbstractObservabilityUnitOfWork` are already imported at the top of `dependencies.py` (`AlertRuleNotFound`/`IncidentNotFound` are confirmed existing in `observability/exceptions.py` per this session's research; `AbstractObservabilityUnitOfWork` per `observability/uow.py:21`) — add the imports if missing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/observability/test_dependencies.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add app/modules/observability/dependencies.py tests/observability/test_dependencies.py
git commit -m "feat(observability): add id-keyed project-permission dependencies for alert_rule and incident"
```

---

## Task 7: Migrate alert-rule PATCH/DELETE and incident acknowledge/resolve/get routes

**Files:**
- Modify: `backend/app/modules/observability/router.py`
- Test: `backend/tests/observability/test_router.py`

**Interfaces:**
- Consumes: `require_project_permission_for_alert_rule`/`require_project_permission_for_incident` (Task 6).
- Produces: 5 more routes migrated. Combined with Task 5's 8, that's 13 of observability's routes now project-role-aware. `GET /incidents` (list) and both webhook routes are explicitly untouched (D8).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/observability/test_router.py`, a new test class proving the decisive id-keyed case (adjust to match this file's existing login-helper pattern, read 2-3 nearby tests first):

```python
class TestProjectRoleGrantsAlertRuleAndIncidentAccess:
    async def test_project_role_grants_alert_rule_update_by_id(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """A collaborator with a project role granting alert_rule.update
        (but no global alert_rule:update) can PATCH /alert-rules/{id} for
        a rule belonging to their project's environment."""
        ...

    async def test_project_role_grants_incident_acknowledge_by_id(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        ...
```

Same note as Task 4 Step 2: read the file's existing helper conventions first, then fill in real bodies — do not run these `...` placeholders as-is.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/observability/test_router.py -k "ProjectRoleGrantsAlertRuleAndIncidentAccess" -v`
Expected: FAIL (403, routes not yet migrated).

- [ ] **Step 3: Migrate the 5 routes**

In `backend/app/modules/observability/router.py`, swap `require_permission(RbacResources.X, RbacActions.Y)` for the matching new factory:

| Route | New dependency | resource | action |
|---|---|---|---|
| `PATCH /alert-rules/{alert_rule_id}` | `require_project_permission_for_alert_rule` | `ALERT_RULE` | `UPDATE` |
| `DELETE /alert-rules/{alert_rule_id}` | `require_project_permission_for_alert_rule` | `ALERT_RULE` | `DELETE` |
| `GET /incidents/{incident_id}` | `require_project_permission_for_incident` | `INCIDENT` | `READ` |
| `POST /incidents/{incident_id}/acknowledge` | `require_project_permission_for_incident` | `INCIDENT` | `ACKNOWLEDGE` |
| `POST /incidents/{incident_id}/resolve` | `require_project_permission_for_incident` | `INCIDENT` | `RESOLVE` |

Do NOT migrate `GET /incidents` (list) or `POST /incidents` (handled separately in Task 8) or either webhook route — per D8, explicitly out of scope.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/observability/test_router.py -v`
Expected: PASS — every existing test plus the 2 new ones. Same error-code-change note as Task 5 Step 5 applies here too (`rbac_permission_denied` → `observability_permission_denied` for these 5 routes specifically) — fix any existing test asserting the old code.

- [ ] **Step 5: Commit**

```bash
git add app/modules/observability/router.py tests/observability/test_router.py
git commit -m "feat(observability): migrate alert-rule/incident id-keyed routes to project-scoped permission"
```

---

## Task 8: `CreateManualIncident` direct-call pattern for body-only environment_id

**Files:**
- Modify: `backend/app/modules/observability/services/create_manual_incident.py` (confirm exact filename first — grep for the class if this path is wrong)
- Modify: `backend/app/modules/observability/dependencies.py` (the `get_create_manual_incident` provider)
- Modify: `backend/app/modules/observability/router.py` (`POST /incidents`)
- Test: `backend/tests/observability/test_services.py`

**Interfaces:**
- Consumes: `ProjectsApi.get_environment_by_id`/`resolve_effective_permissions` (Task 2), `CreateManualIncidentRequest.environment_id: UUID` (confirmed existing field name, `observability/schemas.py:119-123`).
- Produces: `CreateManualIncident.execute(...)` now takes the caller's `UserRead` and does its OWN permission check internally (mirrors `CreateCloudflareConfig`'s existing pattern for `resolve_account_access_grant` — same class of problem, body-only scoping field, no `Depends()` factory can read it at decoration time).

- [ ] **Step 1: Read the current service and router code**

Run: `cd backend && grep -rn "class CreateManualIncident" app/modules/observability/services/`

Read the exact current file in full before editing.

- [ ] **Step 2: Write the failing test**

Add to `backend/tests/observability/test_services.py` (adjust the exact `Fake*` names to match what the file already defines — read it first):

```python
class TestCreateManualIncidentProjectRoleAccess:
    async def test_rejects_a_collaborator_without_incident_create_in_their_effective_grant(self) -> None:
        from app.modules.observability.exceptions import ObservabilityPermissionDenied
        import pytest

        uow = FakeObservabilityUnitOfWork()
        projects_api = FakeProjectsApiNoPermissions()  # returns frozenset() from resolve_effective_permissions
        use_case = CreateManualIncident(uow, projects_api, FakeAuditApi())
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")

        with pytest.raises(ObservabilityPermissionDenied):
            await use_case.execute(
                environment_id=uuid4(),
                category="manual",
                severity="low",
                title="t",
                actor=user,
            )

    async def test_allows_a_collaborator_whose_project_role_grants_incident_create(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        environment_id = uuid4()
        projects_api = FakeProjectsApiWithPermissions(
            environment_id=environment_id,
            project_id=uuid4(),
            permissions=frozenset({"incident.create"}),
        )
        use_case = CreateManualIncident(uow, projects_api, FakeAuditApi())
        user = UserRead.model_construct(id=uuid4(), email="a@b.com", name="A")

        result = await use_case.execute(
            environment_id=environment_id, category="manual", severity="low", title="t", actor=user
        )

        assert result.title == "t"
```

Note: this task's exact `Fake*` helper names (`FakeProjectsApiNoPermissions`, `FakeProjectsApiWithPermissions`, `FakeAuditApi`) are new — either add small local Fakes to `test_services.py` matching this shape, or reuse whatever equivalent Fakes the file already has for `ProjectsApi`/`AuditApi` (check first; observability's services already inject `ProjectsApi` for other use cases like `CreateLokiConfig`, so a `FakeProjectsApi`-shaped test double very likely already exists in this file — extend it with a `resolve_effective_permissions` method rather than creating a duplicate Fake class).

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/observability/test_services.py -k "CreateManualIncidentProjectRoleAccess" -v`
Expected: FAIL — `CreateManualIncident.execute()` doesn't currently accept an `actor` parameter or do any permission check (confirm this by reading the current file in Step 1 first; the exact failure message depends on the current signature).

- [ ] **Step 4: Write minimal implementation**

In the `CreateManualIncident` service file, add the permission check as the first step of `execute()`:

```python
    @use_case
    async def execute(
        self,
        environment_id: UUID,
        category: IncidentCategory,
        severity: AlertSeverity,
        title: str,
        *,
        actor: UserRead,
    ) -> IncidentRead:
        environment = await self._projects_api.get_environment_by_id(environment_id)
        if environment is None:
            raise ObservabilityEnvironmentNotFound()
        permissions = await self._projects_api.resolve_effective_permissions(
            environment.project_id, actor, self._rbac_api
        )
        if "incident.create" not in permissions:
            raise ObservabilityPermissionDenied()

        # ... existing incident-creation logic continues unchanged below,
        # using environment.project_id for the new Incident row's project_id
```

Add `rbac_api: RbacApi` to the constructor if it isn't already injected (check the current `__init__` signature first — it likely already takes `ProjectsApi`/`AuditApi` for the existing environment-validation logic, per the router research above; `RbacApi` is new).

Update `get_create_manual_incident` in `dependencies.py` to inject `RbacApi` if the constructor signature changed:

```python
async def get_create_manual_incident(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    projects_api: ProjectsApi = Depends(get_projects_api),
    rbac_api: RbacApi = Depends(get_rbac_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateManualIncident:
    return CreateManualIncident(uow, projects_api, rbac_api, audit_api)
```

(Adjust constructor argument order to match whatever the actual current file has — read it first per Step 1, don't guess the order blindly here.)

Update the router's `create_manual_incident` handler to pass `actor=user` (resolved from `auth_api.current_user()`, since this route currently likely only gates on `require_permission(INCIDENT, CREATE)` — that Layer-1-only gate should be REMOVED from the route now that the use case does its own project-scoped check, mirroring exactly how `POST /cloudflare-configs` has no Layer-2 `Depends()` today because `CreateCloudflareConfig` does it internally):

```python
@router.post("/incidents")
async def create_manual_incident(
    body: CreateManualIncidentRequest,
    use_case: CreateManualIncident = Depends(get_create_manual_incident),
    auth_api: AuthApi = Depends(get_auth_api),
) -> ApiResponse[IncidentRead]:
    user = auth_api.current_user()
    incident = await use_case.execute(
        environment_id=body.environment_id,
        category=body.category,
        severity=body.severity,
        title=body.title,
        actor=user,
    )
    return ApiResponse[IncidentRead](success=True, data=incident)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_services.py -k "CreateManualIncidentProjectRoleAccess" -v`
Expected: PASS, both tests.

- [ ] **Step 6: Run the full observability test suite**

Run: `cd backend && uv run pytest tests/observability/ -v`
Expected: PASS — every existing test for `CreateManualIncident` still works (confirm none broke from the constructor signature change; update any existing test's use-case instantiation to pass the new `rbac_api`/`actor` params).

- [ ] **Step 7: Commit**

```bash
git add app/modules/observability/services/ app/modules/observability/dependencies.py app/modules/observability/router.py tests/observability/test_services.py
git commit -m "feat(observability): CreateManualIncident resolves project-scoped permission directly (body-only environment_id)"
```

---

## Task 9: Decisive end-to-end integration test

**Files:**
- Modify: `backend/tests/cloudflare/test_router.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4 (this test only exercises cloudflare routes — the observability-side decisive tests were already written inline in Tasks 5/7; this task is the CLOUDFLARE-specific proof, the one with the actual account-manager-bypass claim, on real Postgres).

- [ ] **Step 1: Write the decisive test**

Add to `backend/tests/cloudflare/test_router.py`, in the `TestProjectRoleGrantsEnvironmentScopedCloudflareAccess` class started in Task 4:

```python
    async def test_project_role_grants_tunnel_create_but_never_account_administration(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """The full decisive scenario: admin creates a Cloudflare account,
        binds an environment to it, creates a project role granting
        cloudflare_tunnel.create (from the ASSIGNABLE set), adds a
        collaborator to the project (who holds NO cloudflare_account_managers
        row and NO global cloudflare_tunnel permission), assigns the role.
        The collaborator succeeds on the in-scope Tunnel-create route, and
        is STILL rejected on (a) the excluded binding route and (b) account
        administration — proving the boundary genuinely holds, not just
        that access got broader everywhere."""
        admin_id = await _login_with_permissions(
            client,
            engine,
            permissions=[
                ("cloudflare_account", "create"),
                ("cloudflare_account", "manage_all"),
                ("cloudflare_config", "manage"),
                ("project", "create"),
                ("environment", "create"),
                ("project_member", "manage"),
                ("project_role", "manage"),
                ("project_role", "read"),
                ("project", "read"),
                ("permission", "read"),
            ],
            email="cf-admin@example.com",
        )
        account = (
            await client.post(
                "/api/v1/cloudflare-accounts",
                json={"label": "acct", "cfAccountId": "cf1", "apiToken": "tok"},
            )
        ).json()["data"]
        project = (await client.post("/api/v1/projects", json={"name": "P"})).json()["data"]
        env = (
            await client.post(
                f"/api/v1/projects/{project['id']}/environments", json={"type": "dev", "name": "dev"}
            )
        ).json()["data"]
        await client.post(
            "/api/v1/cloudflare-configs",
            json={"environmentId": env["id"], "cloudflareAccountId": account["id"], "zoneId": "z1"},
        )
        perms_resp = await client.get("/api/v1/rbac/permissions")
        tunnel_create_id = next(
            p["id"]
            for p in perms_resp.json()["data"]
            if p["resource"] == "cloudflare_tunnel" and p["action"] == "create"
        )
        role_resp = await client.post(
            f"/api/v1/projects/{project['id']}/roles",
            json={"name": "tunnel-manager", "permissionIds": [tunnel_create_id]},
        )
        assert role_resp.status_code == 200
        role_id = role_resp.json()["data"]["id"]

        collaborator_id = await _login_with_permissions(
            client, engine, permissions=[("project", "read")], email="collaborator@example.com"
        )
        await _switch_to(client, admin_id, email="cf-admin@example.com")
        await client.post(
            f"/api/v1/projects/{project['id']}/members", json={"userId": str(collaborator_id)}
        )
        assign_resp = await client.put(
            f"/api/v1/projects/{project['id']}/members/{collaborator_id}/role",
            json={"projectRoleId": role_id},
        )
        assert assign_resp.status_code == 200

        await _switch_to(client, collaborator_id, email="collaborator@example.com")

        create_tunnel = await client.post(
            f"/api/v1/environments/{env['id']}/cloudflare-tunnels", json={"name": "t1"}
        )
        assert create_tunnel.status_code == 200

        rebind_attempt = await client.patch(
            f"/api/v1/environments/{env['id']}/cloudflare-config",
            json={"zoneId": "z2"},
        )
        assert rebind_attempt.status_code == 403

        create_account_attempt = await client.post(
            "/api/v1/cloudflare-accounts", json={"label": "x", "cfAccountId": "cf2", "apiToken": "t"}
        )
        assert create_account_attempt.status_code == 403
```

This test reuses `_login_with_permissions`/`_switch_to` — confirm cloudflare's test file has these exact helpers (the original Project Roles plan added `_switch_to` to `tests/projects/test_router.py` this session; cloudflare's own test file may have its own differently-named equivalent, or may need this same `_switch_to` helper added to it — check first, add if missing, matching the exact shape from `tests/projects/test_router.py`).

Also confirm the exact request-body field names used above (`cfAccountId`, `apiToken`, `environmentId`, `cloudflareAccountId`, `zoneId`, `permissionIds`, `userId`, `projectRoleId`) against the real current schemas — these were inferred from patterns established elsewhere in this plan and the original Project Roles plan, but cloudflare's own schemas may use slightly different field names; read `backend/app/modules/cloudflare/schemas.py`'s `CloudflareAccountCreate`/`CloudflareConfigCreate` before running this test and correct any mismatches.

- [ ] **Step 2: Run test to verify it fails initially, then passes after Tasks 1-4/8 land**

Run: `cd backend && uv run pytest tests/cloudflare/test_router.py -k "test_project_role_grants_tunnel_create_but_never_account_administration" -v`
Expected: if Tasks 1-4 are already complete (this task runs after them in sequence), this should PASS immediately — it's the capstone proof, not new production code. If it fails, that's a real signal one of the earlier tasks has a bug; do not move on until it's green.

- [ ] **Step 3: Run the FULL backend suite**

Run: `cd backend && uv run pytest -q`
Expected: every test in `tests/cloudflare/`, `tests/observability/`, `tests/projects/`, `tests/rbac/` passes. (Other unrelated pre-existing failures elsewhere in the suite, if any exist from concurrent work outside this plan's scope, are not this plan's responsibility — but confirm any failure is in a file this plan never touched before treating it as pre-existing.)

- [ ] **Step 4: Commit**

```bash
git add tests/cloudflare/test_router.py
git commit -m "test(cloudflare): decisive end-to-end proof — project role grants tunnel access, never account administration"
```

---

## Task 10: Full verification sweep, frontend confirmation, and finish

**Files:** none (verification only, except a possible zero-line-change confirmation note).

- [ ] **Step 1: Full backend gate**

Run: `cd backend && ruff check . && ruff format --check . && python scripts/check_module_boundaries.py --strict && uv run lint-imports && uv run mypy app/modules/cloudflare/ app/modules/observability/ app/modules/projects/ && uv run pytest -q`
Expected: all green. `ruff check .`/`ruff format --check .` on the WHOLE repo may surface pre-existing, unrelated debt in files this plan never touched (this session has already established this pattern is common when other concurrent work is in progress) — if so, re-run scoped to just this plan's touched files (`app/modules/cloudflare/ app/modules/observability/ app/modules/projects/ tests/cloudflare/ tests/observability/ tests/projects/`) and confirm THAT scope is clean; don't fix unrelated files.

- [ ] **Step 2: Confirm the frontend needs zero changes**

Read `frontend/src/modules/projects/ui/project-role-form-dialog.tsx` and `frontend/src/modules/projects/api/fetchers.ts` in full. Confirm: (a) `ProjectRolePermissionItem` already has `{id, resource, action, descriptionKey}` with no hardcoded resource allowlist anywhere in the dialog's rendering code, (b) the checkbox grid groups by `perm.resource` generically via `Object.entries(groupedPermissions)`, with no switch/if-chain naming specific resources. If both hold, no frontend code change is needed — the new `cloudflare_dns`/`cloudflare_tunnel`/`cloudflare_hostname`/`cloudflare_config`/`cloudflare_audit`/`loki_config`/`alert_rule`/`incident` groups will render automatically once `GET /projects/assignable-permissions` starts returning them (which it does automatically once Task 1's `ASSIGNABLE` change lands, since `ListAssignablePermissions` filters the full RBAC catalog by `ProjectRoleRules.assignable_keys()` with no resource-specific logic).

If either assumption is FALSE (e.g. a hardcoded resource list exists somewhere), stop and add a real task here to fix it — do not silently skip.

- [ ] **Step 3: i18n check for the new catalog entries' display labels**

Every atom added in Task 1 already has a `description_key` in `RbacPermissionCatalog.CATALOG` (e.g. `permissions.cloudflare_dns.create`) and a matching translation in `frontend/locales/{en,vi}/modules/roles.json`'s `catalog.cloudflare_dns.create` (these already exist — this plan adds NO new rbac catalog rows, only reuses existing ones). Spot-check 2-3 entries in both locale files to confirm the keys are genuinely present (they should be, since these atoms already power the global Roles admin page today) — if any are missing, that's a pre-existing gap unrelated to this plan, note it but don't fix it here.

- [ ] **Step 4: Manual verification against `itsm_test`**

Run the full decisive scenario from Task 9 manually against a locally-running backend pointed at `itsm_test` (`DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test"`) — **never** any other database. If a manual UI walkthrough is wanted too, re-seed `itsm_test`'s RBAC catalog first (`DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run python -m app.seeds.seed_rbac`) since this plan adds no catalog rows but the frontend project-role editor needs the catalog seeded to render checkboxes at all.

- [ ] **Step 5: `reviewing-code-against-skills` pass**

Run the `reviewing-code-against-skills` skill against the full diff (`git diff develop...HEAD --stat` first to confirm scope) — `fastapi-modular-scaffold` conventions for every backend file touched. Fix loop capped at 2 rounds per this session's established convention.

- [ ] **Step 6: `finishing-a-development-branch`**

Branch this work as `feature/env-scoped-cloudflare-loki-alerting-project-roles` off `develop` (confirm you're actually on this branch, not committing directly — Hard Rule #8, non-negotiable). Present the standard 3-option menu, wait for explicit choice before any merge action — same as every other feature this session.

---

## Self-Review (performed while writing this plan, per the skill's own requirement)

**Spec coverage:** D1 (Task 1's `ASSIGNABLE` additions + exclusions, Task 9's negative-case assertions). D2 (stated as Global Constraint, enforced structurally by Task 3's design — `resolve_effective_permissions` is the plain unioned set with no source distinction, exactly as decided). D3 (Task 3's `require_cloudflare_environment_access`, tested for both the unchanged-existing-path and the new-fallback-path plus the both-fail case). D4 (Task 2). D5 (Task 5 — Loki + environment-keyed alert-rule routes). D6 (Task 6 — the two new id-keyed dependencies, grounded in the CONFIRMED real model columns: `Incident.project_id` direct, `AlertRule.environment_id` only). D7 (Task 8 — `CreateManualIncident`'s direct-call pattern). D8 (explicitly listed as untouched in Tasks 4 and 7's route tables, restated in the Global Constraints). D9 (Task 1, same task as D1 — folded together since they're the same catalog edit).

**Placeholder scan:** Two intentional exceptions flagged explicitly in-line (Task 4 Step 2, Task 7 Step 1) where the exact test body depends on reading a co-located test file's existing helper conventions first — each is accompanied by a real, concrete, runnable code skeleton and an explicit instruction for what "fill in" means, not a bare "TODO." Every other step has complete, real code. No "add appropriate error handling"/"handle edge cases" language anywhere.

**Type consistency:** `require_cloudflare_environment_access(resource: str, action: str, min_level: AccessLevel) -> Depends(...) -> AccountAccessGrant` (Task 3) is consumed identically in Task 4's route migrations. `require_project_permission_for_environment`/`_for_alert_rule`/`_for_incident` all return `UserRead` consistently (Tasks 5, 6, 7) — deliberately NOT `ProjectPermissionGrant` (which is projects-module-private, not exported via `public.py`), since observability's routes never needed the full grant object, only the resolved `user` for audit-actor purposes, matching what their CURRENT `require_permission`-gated routes already receive today (byte-for-byte return-type compatibility, zero router-body changes needed beyond the `Depends()` swap itself). `ProjectsApi.resolve_effective_permissions(project_id, user, rbac_api) -> frozenset[str]` (Task 2) is the single signature every later task's dependency factories call identically.

**One known gap surfaced honestly:** `GET /incidents` (list, D8) stays globally gated — a collaborator with project-scoped `incident.read` via a project role will NOT see project-scoped incidents show up in the list endpoint unless they also hold the global `incident.read` permission, only the id-keyed detail/acknowledge/resolve routes benefit from this plan. This mirrors the original Project Roles plan's own `GET /projects` limitation exactly and is disclosed the same way, not silently different.
