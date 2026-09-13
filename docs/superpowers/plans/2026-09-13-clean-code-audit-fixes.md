# Clean Code Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the audit findings that survived verification: lost root causes in Cloudflare compensation paths, an N+1 in `ProjectRoleRepository`, untyped `ValueError`s in repositories, unvalidated frontend fetchers, misplaced/hardcoded constants, a thin-page violation and a few non-i18n strings.

**Architecture:** Backend changes stay inside each module's own layers (repository raises its module's `*NotFound`; services only gain `exc_info`). Frontend changes move wire types into zod schemas under each owner's `model/`, keep module-only concepts in their module, move `ACCESS_LEVEL` next to `MANAGED_BY` in `shared/constants/cloudflare.ts`, and extract the dashboard page body into a new `modules/dashboard`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, pytest + testcontainers (Docker required); Next.js App Router, zod v4, TanStack Query, next-intl, vitest.

**Spec:** `notes/clean_code_audit.md` (the audit) plus the verified review of it. Only the review's "fix" items are in scope; see "Scope".

## Global Constraints

- Work on branch `refactor/clean-code-audit-fixes` (stacked on `feature/project-scoped-notifications-ui-polish`). Local commits only — no push, no merge.
- One Conventional Commit per task, message ending with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- fastapi-modular-scaffold rule #18: inside a module, `constants → exceptions → … → repository → services`; a repository may import its own module's `exceptions.py`.
- fastapi-modular-scaffold `references/layer-examples.md`: a repository raises the module's domain `*NotFound` (e.g. `CatalogRepository.set_status` → `CatalogNotFound`).
- nextjs-modular-architecture: fetchers call `apiFetch<unknown>` and `.parse()` with a zod schema from `model/`; types are `z.infer`; "Only one module uses it → keep inside `modules/<name>/`"; modules never import other modules; no proxy re-exports; `app/` pages stay thin.
- AGENTS.md rule 12: typed constants from `shared/constants/` for auth/RBAC/roles/statuses — never string literals.
- Every user-facing string goes through next-intl with both `en` and `vi` entries.
- `ui-ux-pro-max` is invoked during implementation of every UI-touching task (Tasks 5, 10, 11, 12).

---

## Scope

**In:**
1. Compensation paths in 6 Cloudflare services log the exception that triggered them (`exc_info=True`).
2. `ProjectRoleRepository.list_page` / `list_for_project` load permissions in one query.
3. 19 `raise ValueError(...)` sites (7 files) raise the owning module's `*NotFound`.
4. Frontend fetchers that return data without zod validation: `modules/projects` (12), `modules/cloudflare-accounts` (4), `entities/permission` (1).
5. `ACCESS_LEVEL` → `shared/constants/cloudflare.ts`; `CloudflareAccountManager` becomes a zod schema; badge switch uses constants (dead `"admin"` case becomes `EDITOR`).
6. Remove the unused `AUTH_STATUS` re-export from `modules/auth`; export `LanguageSwitch`/`useLogout` from `modules/auth/index.ts` so the sidebar stops deep-importing.
7. `api-client.ts`: bypass paths and the `auth_not_authenticated` code come from constants.
8. `shared/ui/icons/index.ts`: named re-exports instead of `export *`.
9. `DNS_TYPE_COLORS` typed `Record<DnsType, string>` (adds the missing `HTTPS`).
10. Hardcoded `title` strings in `cloudflare-account-detail-view.tsx` / `account-dns-tab.tsx` → i18n.
11. Dashboard page body → `modules/dashboard/ui/dashboard-view.tsx`; `"Operator"`/`"MEMBER"` fallbacks → i18n.

**Out:** splitting `cloudflare/repository.py` / `router.py`; audit 1.4 (merging the two DNS type lists — different concepts), 2.1/5.1 (moving single-module schemas to `entities/`), 4.3 (narrowing `except Exception` — would skip compensation), 5.2; optional 3.2 (`assert`s) and a shared compensation helper; the remaining hardcoded English copy inside the dashboard cards.

## Plugins

- superpowers: `writing-plans` used for this plan; execution inline with `executing-plans` (no subagents — not requested).
- ui-ux-pro-max: invoked in Phase 3 for Task 5 (editor badge colour), Task 10 (HTTPS badge colour, contrast), Task 11 (title/aria copy), Task 12 (dashboard move — no visual change).

## Impact Assessment (GitNexus, upstream)

| Symbol | Risk | Notes / mitigation |
|---|---|---|
| `ProjectRoleRepository` | MEDIUM (42) | Return type and ordering unchanged; new integration test asserts statement count and permission ids. |
| `RoleRepository` | MEDIUM (39) | Only the missing-row branch of `update` changes exception type. |
| `UserRepository` | MEDIUM (56) | Same — `update_profile` / `set_status` missing-row branch. |
| `DnsRecordRepository` | MEDIUM (49) | Same — `update` missing-row branch; callers wrap it in `except Exception`, so compensation still runs. |
| `NotificationChannelRepository`, `AlertRuleRepository` | LOW | Missing-row branch only. |
| `CloudflareApi.ensure_webhook_destination` | LOW (0) | Missing-account branch only. |
| `UpdateDnsRecord` (+5 sibling services) | LOW | Logging kwargs only. |
| `fetchProjectPermissions` | **HIGH** (4 direct, 3 processes) | Schema mirrors `ProjectPermissionSetRead` (`project_id: UUID`, `permissions: list[str]`) exactly; unit test parses a real-shaped payload; typecheck + existing permission tests must stay green. |
| `fetchProjectRoles`, `fetchCloudflareAccountManagers` | LOW | Schemas mirror `ProjectRoleRead` / `CloudflareAccountManagerRead`; unknown fields are stripped, not rejected. |
| `isAuthBypassUrl` | LOW (28) | Same three path fragments, now from constants. |
| `ACCESS_LEVEL`, `DNS_TYPE_COLORS`, `DashboardPage` | LOW | Import-path / typing changes. |

## Architecture Impact

- **FastAPI modules:** projects, cloudflare, observability, users, notifications, rbac (repositories); cloudflare (6 services, `public.py`).
- **Next.js:** `modules/projects` (new `model/schema.ts`), `modules/cloudflare-accounts` (new `model/schema.ts`), `entities/permission` (new `model/schema.ts`), `modules/auth` (index exports), new `modules/dashboard`, `shared/constants/{auth,api,cloudflare}.ts`, `shared/lib/api-client.ts`, `shared/ui/icons/index.ts`.
- **UI surfaces:** dashboard (moved, no visual change), Cloudflare account detail (editor badge colour, tooltips), account DNS tab (HTTPS badge colour, tooltips).

## Risks

- A zod schema stricter than the real payload breaks a page at runtime → schemas copy the backend `*Read` models field by field, optional backend fields use `.nullish()`, and each schema gets a parse test with a backend-shaped payload.
- `caplog` might not see records if logging config stops propagation → if Task 1's test cannot observe records, assert via a `logging.Handler` attached directly to the service's logger instead.
- Backend tests need Docker (Postgres/Mongo testcontainers).

---

### Task 1: Log the root cause in Cloudflare compensation paths

**Files:**
- Modify: `backend/app/modules/cloudflare/services/create_dns_record.py`, `update_dns_record.py`, `delete_dns_record.py`, `add_tunnel_hostname.py`, `update_tunnel_hostname.py`, `remove_tunnel_hostname.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:** Consumes nothing new. Produces nothing new (behaviour: CRITICAL records carry `exc_info`).

- [ ] **Step 1: Write the failing assertions**

Add near the other module-level helpers in `tests/cloudflare/test_services.py` (add `import logging` to the imports if absent):

```python
def _assert_first_critical_log_carries_exception(caplog: pytest.LogCaptureFixture) -> None:
    """The first CRITICAL record is the failed local write. The use case
    re-raises `from None`, so this record is the only place its cause survives."""
    critical = [record for record in caplog.records if record.levelno == logging.CRITICAL]
    assert critical, "expected a CRITICAL log for the failed local write"
    assert critical[0].exc_info is not None
```

In each of these six tests, add `caplog: pytest.LogCaptureFixture` to the signature and call `_assert_first_critical_log_carries_exception(caplog)` right after its `with pytest.raises(...)` block:
- `TestCreateDnsRecord` — the test raising `DnsRecordSyncFailed`
- `TestUpdateDnsRecord.test_local_failure_after_cf_success_attempts_compensating_revert`
- `TestDeleteDnsRecord` — the test raising `DnsRecordSyncFailed`
- `TestAddTunnelHostname.test_local_write_failure_triggers_compensating_put_back_and_raises_sync_failed`
- `TestUpdateTunnelHostname` — the test raising `TunnelIngressSyncFailed`
- `TestRemoveTunnelHostname` — the test raising `TunnelIngressSyncFailed`

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -q -k "SyncFailed or compensating or failure"`
Expected: the six tests FAIL on `assert critical[0].exc_info is not None`.

- [ ] **Step 3: Add `exc_info=True` to every CRITICAL call inside an `except` block**

`update_dns_record.py` (outer and inner `except`):

```python
        except Exception:
            logger.critical(
                "Local DNS record update failed after Cloudflare PATCH succeeded — attempting "
                "compensating revert (zone_id=%s, cf_record_id=%s)",
                config.zone_id,
                existing.cf_record_id,
                exc_info=True,
            )
            ...
            except Exception:
                logger.critical(
                    "Cloudflare/local state now DIVERGED — compensating revert ALSO failed, manual "
                    "reconciliation required (zone_id=%s, cf_record_id=%s)",
                    config.zone_id,
                    existing.cf_record_id,
                    exc_info=True,
                )
```

`create_dns_record.py`: same two calls ("Local DNS record write failed …", "ORPHAN DNS RECORD on Cloudflare …") gain `exc_info=True`.
`delete_dns_record.py`: the single call ("DNS record deleted on Cloudflare but local delete failed …") gains `exc_info=True`.
`add_tunnel_hostname.py`, `update_tunnel_hostname.py`, `remove_tunnel_hostname.py`: the "Local tunnel hostname … failed after Cloudflare PUT succeeded …" and "Compensating PUT-back ALSO failed …" calls gain `exc_info=True`. The "… succeeded" calls stay unchanged.

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** — `fix(cloudflare): log the failure that triggers a compensating Cloudflare call`

---

### Task 2: Batch-load project role permissions

**Files:**
- Modify: `backend/app/modules/projects/repository.py` (`ProjectRoleRepository`)
- Create: `backend/tests/projects/test_repository.py`

**Interfaces:** Produces `ProjectRoleRepository._load_many(rows: list[ProjectRole]) -> list[ProjectRoleRow]` (private helper). `list_page` / `list_for_project` signatures unchanged.

- [ ] **Step 1: Write the failing tests** — create `tests/projects/test_repository.py`:

```python
"""Integration tests for the projects repositories — real Postgres via a
locally scoped session fixture, mirroring tests/cloudflare/test_repository.py.
Nothing here commits: the session is rolled back after each test."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRoleRepository
from app.modules.rbac.models import Permission


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@contextmanager
def _count_statements(engine: AsyncEngine) -> Iterator[list[str]]:
    """Collects every SQL statement the engine sends while the block runs."""
    statements: list[str] = []

    def _record(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)


async def _make_project(session: AsyncSession) -> Project:
    project = Project(name=f"P-{uuid4()}")
    session.add(project)
    await session.flush()
    return project


async def _make_permissions(session: AsyncSession, count: int) -> list[UUID]:
    rows = [
        Permission(resource=f"test_{uuid4().hex[:12]}", action="read", description_key="permissions.test.read")
        for _ in range(count)
    ]
    session.add_all(rows)
    await session.flush()
    return [row.id for row in rows]


async def _make_three_roles(session: AsyncSession) -> tuple[Project, ProjectRoleRepository]:
    project = await _make_project(session)
    permission_ids = await _make_permissions(session, 3)
    repo = ProjectRoleRepository(session)
    for index in range(3):
        await repo.create(project_id=project.id, name=f"role-{index}", permission_ids=permission_ids[: index + 1])
    return project, repo


class TestProjectRoleRepositoryBatchLoading:
    async def test_list_for_project_loads_all_permissions_in_one_query(
        self, _session: AsyncSession, engine: AsyncEngine
    ) -> None:
        project, repo = await _make_three_roles(_session)

        with _count_statements(engine) as statements:
            roles = await repo.list_for_project(project.id)

        assert [len(role.permission_ids) for role in roles] == [1, 2, 3]
        assert len(statements) == 2

    async def test_list_page_loads_all_permissions_in_one_query(
        self, _session: AsyncSession, engine: AsyncEngine
    ) -> None:
        _, repo = await _make_three_roles(_session)

        with _count_statements(engine) as statements:
            roles, total = await repo.list_page(limit=50, offset=0)

        assert total == 3
        assert sorted(len(role.permission_ids) for role in roles) == [1, 2, 3]
        assert len(statements) == 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/projects/test_repository.py -q`
Expected: FAIL — `assert 4 == 2` and `assert 5 == 3` (one permission query per role).

- [ ] **Step 3: Implement** — in `ProjectRoleRepository`, add the helper after `_load_by_id` and use it:

```python
    @helper
    async def _load_many(self, rows: list[ProjectRole]) -> list[ProjectRoleRow]:
        """Batch counterpart of _load_by_id: one permission query for every
        row instead of one per row."""
        if not rows:
            return []
        links = await self._session.execute(
            select(ProjectRolePermission.project_role_id, ProjectRolePermission.permission_id).where(
                ProjectRolePermission.project_role_id.in_([row.id for row in rows])
            )
        )
        permission_ids: dict[UUID, list[UUID]] = {row.id: [] for row in rows}
        for project_role_id, permission_id in links:
            permission_ids[project_role_id].append(permission_id)
        return [
            ProjectRoleRow(
                id=row.id,
                project_id=row.project_id,
                name=row.name,
                permission_ids=permission_ids[row.id],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[ProjectRoleRow], int]:
        rows = list(
            await self._session.scalars(select(ProjectRole).order_by(ProjectRole.id).limit(limit).offset(offset))
        )
        items = await self._load_many(rows)
        total = await self._session.scalar(select(func.count()).select_from(ProjectRole))
        return items, total or 0

    @database
    async def list_for_project(self, project_id: UUID) -> list[ProjectRoleRow]:
        rows = list(
            await self._session.scalars(
                select(ProjectRole).where(ProjectRole.project_id == project_id).order_by(ProjectRole.name)
            )
        )
        return await self._load_many(rows)
```

- [ ] **Step 4: Run to verify they pass** — `uv run pytest tests/projects -q` → PASS.
- [ ] **Step 5: Commit** — `perf(projects): load project role permissions in one query`

---

### Task 3: Repositories raise their module's NotFound

**Files:**
- Modify: `backend/app/modules/projects/repository.py`, `cloudflare/repository.py`, `cloudflare/public.py`, `observability/repository.py`, `users/repository.py`, `notifications/repository.py`, `rbac/repository.py`
- Test: `backend/tests/projects/test_repository.py`, `tests/cloudflare/test_repository.py`, `tests/cloudflare/test_public.py`, `tests/observability/test_repository.py`, `tests/notifications/test_repository.py`
- Create: `backend/tests/users/test_repository.py`, `backend/tests/rbac/test_repository.py`

**Mapping (site → exception):**

| File | Method | Raises |
|---|---|---|
| projects/repository.py | `ProjectRepository.update` | `ProjectNotFound` |
| | `EnvironmentRepository.update` | `EnvironmentNotFound` |
| | `ProjectLinkRepository.update` | `ProjectLinkNotFound` |
| | `ProjectRoleRepository.update` | `ProjectRoleNotFound` |
| cloudflare/repository.py | `CloudflareAccountRepository.update`, `.set_webhook_destination` | `CloudflareAccountNotFound` |
| | `CloudflareConfigRepository.update_by_environment_id` | `CloudflareConfigNotFound` |
| | `DnsRecordRepository.update` | `DnsRecordNotFound` |
| | `CloudflareTunnelRepository.update_status` | `CloudflareTunnelNotFound` |
| | `TunnelHostnameRepository.update_service` | `TunnelPublicHostnameNotFound` |
| cloudflare/public.py | `CloudflareApi.ensure_webhook_destination` | `CloudflareAccountNotFound` |
| observability/repository.py | `LokiConfigRepository.update_by_environment_id` | `LokiConfigNotFound` |
| | `AlertRuleRepository.set_cf_policy_id`, `.update` | `AlertRuleNotFound` |
| | `IncidentRepository.update_status` | `IncidentNotFound` |
| users/repository.py | `UserRepository.update_profile`, `.set_status` | `UserNotFound` |
| notifications/repository.py | `NotificationChannelRepository.update` | `NotificationChannelNotFound` |
| rbac/repository.py | `RoleRepository.update` | `RoleNotFound` |

- [ ] **Step 1: Write the failing tests**

Append to `tests/projects/test_repository.py` (add imports `from app.integrations.cache.client import CacheClient`, `from app.modules.projects.exceptions import EnvironmentNotFound, ProjectLinkNotFound, ProjectNotFound, ProjectRoleNotFound`, `from app.modules.projects.repository import EnvironmentRepository, ProjectLinkRepository, ProjectRepository`):

```python
class TestUpdatesRaiseNotFoundForMissingRows:
    async def test_project(self, _session: AsyncSession) -> None:
        with pytest.raises(ProjectNotFound):
            await ProjectRepository(_session, CacheClient.__new__(CacheClient)).update(
                uuid4(), name="x", description=None
            )

    async def test_environment(self, _session: AsyncSession) -> None:
        with pytest.raises(EnvironmentNotFound):
            await EnvironmentRepository(_session, CacheClient.__new__(CacheClient)).update(
                uuid4(), name="x", base_url=None
            )

    async def test_project_link(self, _session: AsyncSession) -> None:
        with pytest.raises(ProjectLinkNotFound):
            await ProjectLinkRepository(_session).update(uuid4(), name="x", url=None)

    async def test_project_role(self, _session: AsyncSession) -> None:
        with pytest.raises(ProjectRoleNotFound):
            await ProjectRoleRepository(_session).update(uuid4(), name="x", permission_ids=None)
```

Append to `tests/cloudflare/test_repository.py` (import `TunnelStatus` with `DnsRecordType`; import the five exceptions from `app.modules.cloudflare.exceptions`):

```python
class TestUpdatesRaiseNotFoundForMissingRows:
    async def test_account_update(self, _session: AsyncSession) -> None:
        with pytest.raises(CloudflareAccountNotFound):
            await CloudflareAccountRepository(_session, CacheClient.__new__(CacheClient)).update(
                uuid4(), label="x", api_token=None
            )

    async def test_account_set_webhook_destination(self, _session: AsyncSession) -> None:
        with pytest.raises(CloudflareAccountNotFound):
            await CloudflareAccountRepository(_session, CacheClient.__new__(CacheClient)).set_webhook_destination(
                uuid4(), cf_webhook_destination_id="wh", secret_ciphertext="c"
            )

    async def test_config(self, _session: AsyncSession) -> None:
        with pytest.raises(CloudflareConfigNotFound):
            await CloudflareConfigRepository(_session).update_by_environment_id(
                uuid4(), cloudflare_account_id=uuid4(), zone_id="z", zone_name="a.com"
            )

    async def test_dns_record(self, _session: AsyncSession) -> None:
        with pytest.raises(DnsRecordNotFound):
            await DnsRecordRepository(_session).update(uuid4(), content="1.1.1.1", priority=None, proxied=False, ttl=1)

    async def test_tunnel(self, _session: AsyncSession) -> None:
        with pytest.raises(CloudflareTunnelNotFound):
            await CloudflareTunnelRepository(_session).update_status(
                uuid4(), status=TunnelStatus.HEALTHY, last_synced_at=datetime.now(UTC)
            )

    async def test_tunnel_hostname(self, _session: AsyncSession) -> None:
        with pytest.raises(TunnelPublicHostnameNotFound):
            await TunnelHostnameRepository(_session).update_service(uuid4(), service="http://x")
```

Append to `TestEnsureWebhookDestination` in `tests/cloudflare/test_public.py` (import `CloudflareAccountNotFound`):

```python
    async def test_raises_account_not_found_for_unknown_account(self) -> None:
        api = CloudflareApi(FakeUow(FakeAccountsRepo()), client=FakeCloudflareClient(), projects_api=object())

        with pytest.raises(CloudflareAccountNotFound):
            await api.ensure_webhook_destination(uuid4(), webhook_url="https://x")
```

Append to `tests/observability/test_repository.py` (import `AlertRuleNotFound, IncidentNotFound, LokiConfigNotFound` from `app.modules.observability.exceptions`):

```python
class TestUpdatesRaiseNotFoundForMissingRows:
    async def test_loki_config(self, _session: AsyncSession) -> None:
        with pytest.raises(LokiConfigNotFound):
            await LokiConfigRepository(_session).update_by_environment_id(
                uuid4(),
                endpoint_url="http://loki:3100",
                tenant_id=None,
                auth_type=LokiAuthType.NONE,
                credential=None,
                default_query='{job="app"}',
                default_range_minutes=15,
            )

    async def test_alert_rule_set_cf_policy_id(self, _session: AsyncSession) -> None:
        with pytest.raises(AlertRuleNotFound):
            await AlertRuleRepository(_session).set_cf_policy_id(uuid4(), cf_policy_id="p")

    async def test_alert_rule_update(self, _session: AsyncSession) -> None:
        with pytest.raises(AlertRuleNotFound):
            await AlertRuleRepository(_session).update(uuid4(), name="x")

    async def test_incident(self, _session: AsyncSession) -> None:
        with pytest.raises(IncidentNotFound):
            await IncidentRepository(_session).update_status(
                uuid4(), status=IncidentStatus.ACKNOWLEDGED, actor_id=None, at=datetime.now(UTC)
            )
```

Append to `TestNotificationChannelRepository` in `tests/notifications/test_repository.py` (import `NotificationChannelNotFound`):

```python
    async def test_update_raises_channel_not_found_for_missing_row(self, _session: AsyncSession) -> None:
        with pytest.raises(NotificationChannelNotFound):
            await NotificationChannelRepository(_session).update(uuid4(), name="x", config=None, is_active=None)
```

Create `tests/users/test_repository.py`:

```python
"""Integration tests for the users repository — real Postgres via a locally
scoped session fixture, mirroring tests/cloudflare/test_repository.py."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.cache.client import CacheClient
from app.modules.common.constants import UserStatus
from app.modules.users.exceptions import UserNotFound
from app.modules.users.repository import UserRepository


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


class TestUpdatesRaiseNotFoundForMissingRows:
    async def test_update_profile(self, _session: AsyncSession) -> None:
        with pytest.raises(UserNotFound):
            await UserRepository(_session, CacheClient.__new__(CacheClient)).update_profile(
                uuid4(),
                email="a@x.com",
                name="A",
                external_user_id="ext-1",
                employee_code=None,
                email_confirmed=True,
            )

    async def test_set_status(self, _session: AsyncSession) -> None:
        with pytest.raises(UserNotFound):
            await UserRepository(_session, CacheClient.__new__(CacheClient)).set_status(uuid4(), UserStatus.BLOCKED)
```

Create `tests/rbac/test_repository.py`:

```python
"""Integration tests for the rbac repository — real Postgres via a locally
scoped session fixture, mirroring tests/cloudflare/test_repository.py."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.cache.client import CacheClient
from app.modules.rbac.exceptions import RoleNotFound
from app.modules.rbac.repository import RoleRepository


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


class TestRoleRepositoryUpdate:
    async def test_raises_role_not_found_for_missing_row(self, _session: AsyncSession) -> None:
        with pytest.raises(RoleNotFound):
            await RoleRepository(_session, CacheClient.__new__(CacheClient)).update(
                uuid4(), name="x", permission_ids=None
            )
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/projects/test_repository.py tests/cloudflare/test_repository.py tests/cloudflare/test_public.py tests/observability/test_repository.py tests/notifications/test_repository.py tests/users/test_repository.py tests/rbac/test_repository.py -q`
Expected: the 19 new tests FAIL with `ValueError: … does not exist`.

- [ ] **Step 3: Implement** — in each file add the module's exception import between its `constants` and `models` imports, then replace each `raise ValueError(f"… does not exist")` with the mapped exception, no arguments, e.g.:

```python
from app.modules.projects.exceptions import (
    EnvironmentNotFound,
    ProjectLinkNotFound,
    ProjectNotFound,
    ProjectRoleNotFound,
)
...
        row = await self._session.get(Project, project_id)
        if row is None:
            raise ProjectNotFound()
```

Imports per file:
- `cloudflare/repository.py`: `from app.modules.cloudflare.exceptions import (CloudflareAccountNotFound, CloudflareConfigNotFound, CloudflareTunnelNotFound, DnsRecordNotFound, TunnelPublicHostnameNotFound)`
- `cloudflare/public.py`: `from app.modules.cloudflare.exceptions import CloudflareAccountNotFound` (after the `dependencies` import)
- `observability/repository.py`: `from app.modules.observability.exceptions import AlertRuleNotFound, IncidentNotFound, LokiConfigNotFound`
- `users/repository.py`: `from app.modules.users.exceptions import UserNotFound`
- `notifications/repository.py`: `from app.modules.notifications.exceptions import NotificationChannelNotFound`
- `rbac/repository.py`: `from app.modules.rbac.exceptions import RoleNotFound`

- [ ] **Step 4: Run to verify they pass** — same command → PASS; then `uv run ruff check app tests && uv run lint-imports`.
- [ ] **Step 5: Commit** — `refactor(backend): raise module NotFound errors from repositories instead of ValueError`

---

### Task 4: Validate project fetchers with zod

**Files:**
- Create: `frontend/src/modules/projects/model/schema.ts`, `frontend/src/modules/projects/model/schema.test.ts`
- Modify: `frontend/src/modules/projects/api/fetchers.ts`, `modules/projects/index.ts`, `ui/project-link-form-dialog.tsx`, `ui/project-role-form-dialog.tsx`, `ui/project-roles-section.tsx`, `ui/project-detail/project-links-section.tsx`, `ui/project-detail/project-members-panel.tsx`

**Interfaces:** Produces `PROJECT_LINK_TYPE`, `ProjectLinkType`, `projectLinkSchema`/`ProjectLink`, `projectMemberSchema`/`ProjectMember`, `projectRoleSchema`/`ProjectRole` from `modules/projects/model/schema.ts`. Consumes `projectSchema`/`Project` (`@/entities/project`), `environmentSchema`/`Environment` (`@/entities/environment`), `permissionSchema`/`PermissionItem` (`@/entities/role`).

- [ ] **Step 1: Write the failing test** — `modules/projects/model/schema.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { projectLinkSchema, projectMemberSchema, projectRoleSchema } from "./schema";

const ID = "b3f1c2e4-1111-4444-8888-000000000000";
const OTHER_ID = "b3f1c2e4-2222-4444-8888-000000000000";

describe("projects model schemas", () => {
  it("parses a link and strips backend-only timestamps", () => {
    const parsed = projectLinkSchema.parse({
      id: ID, projectId: OTHER_ID, type: "jira", name: "Board", url: "https://x", isDefault: true,
      createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed).toEqual({ id: ID, projectId: OTHER_ID, type: "jira", name: "Board", url: "https://x", isDefault: true });
  });

  it("parses a member without a project role", () => {
    const parsed = projectMemberSchema.parse({
      userId: ID, name: "A", email: "a@x.com", createdAt: "2026-01-01T00:00:00Z",
      projectRoleId: null, projectRoleName: null,
    });
    expect(parsed.projectRoleId).toBeNull();
  });

  it("parses a role with its permissions", () => {
    const parsed = projectRoleSchema.parse({
      id: ID, projectId: OTHER_ID, name: "Ops",
      permissions: [{ id: OTHER_ID, resource: "project_incident", action: "read", descriptionKey: "permissions.project_incident.read" }],
      createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed.permissions).toHaveLength(1);
  });

  it("rejects an unknown link type", () => {
    expect(() => projectLinkSchema.parse({ id: ID, projectId: OTHER_ID, type: "slack", name: "x", url: "x", isDefault: false })).toThrow();
  });
});
```

- [ ] **Step 2: Run** — `cd frontend && pnpm test src/modules/projects/model/schema.test.ts` → FAIL (module not found).

- [ ] **Step 3: Implement** — `modules/projects/model/schema.ts`:

```ts
import { z } from "zod";
import { permissionSchema } from "@/entities/role";

export const PROJECT_LINK_TYPE = {
  JIRA: "jira",
  GIT: "git",
  OTHER: "other",
} as const;
export type ProjectLinkType = (typeof PROJECT_LINK_TYPE)[keyof typeof PROJECT_LINK_TYPE];

export const projectLinkSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  type: z.enum([PROJECT_LINK_TYPE.JIRA, PROJECT_LINK_TYPE.GIT, PROJECT_LINK_TYPE.OTHER]),
  name: z.string(),
  url: z.string(),
  isDefault: z.boolean(),
});
export type ProjectLink = z.infer<typeof projectLinkSchema>;

export const projectMemberSchema = z.object({
  userId: z.uuid(),
  name: z.string(),
  email: z.string(),
  createdAt: z.string(),
  projectRoleId: z.uuid().nullish(),
  projectRoleName: z.string().nullish(),
});
export type ProjectMember = z.infer<typeof projectMemberSchema>;

export const projectRoleSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  name: z.string(),
  permissions: z.array(permissionSchema),
});
export type ProjectRole = z.infer<typeof projectRoleSchema>;
```

`modules/projects/api/fetchers.ts` — drop the three interfaces; every data-returning call becomes `apiFetch<unknown>` + parse:

```ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { projectSchema, type Project } from "@/entities/project";
import { environmentSchema, type Environment } from "@/entities/environment";
import { permissionSchema, type PermissionItem } from "@/entities/role";
import {
  projectLinkSchema,
  projectMemberSchema,
  projectRoleSchema,
  type ProjectLink,
  type ProjectMember,
  type ProjectRole,
} from "../model/schema";

export async function createProject(name: string, description?: string): Promise<Project> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ROOT, { method: "POST", data: { name, description } });
  return projectSchema.parse(raw);
}
// updateProject → projectSchema; createEnvironment/updateEnvironment → environmentSchema;
// fetchProjectLinks → projectLinkSchema.array(); createProjectLink/updateProjectLink → projectLinkSchema;
// fetchProjectMembers → projectMemberSchema.array(); fetchProjectRoles → projectRoleSchema.array();
// fetchAssignablePermissions → permissionSchema.array() returning PermissionItem[];
// createProjectRole/updateProjectRole → projectRoleSchema. Void calls stay apiFetch<null>.
```

Consumers: import types from `model/schema` instead of `api/fetchers`:
- `ui/project-roles-section.tsx`: `import { fetchProjectRoles } from "../api/fetchers";` + `import type { ProjectRole } from "../model/schema";`
- `ui/project-role-form-dialog.tsx`: `import { fetchAssignablePermissions } from "../api/fetchers";`, `import type { ProjectRole } from "../model/schema";`, `import type { PermissionItem } from "@/entities/role";` and rename `ProjectRolePermissionItem` → `PermissionItem` in the file.
- `ui/project-detail/project-links-section.tsx` and `project-members-panel.tsx`: same split with `../../model/schema`.
- `ui/project-link-form-dialog.tsx`: `import { PROJECT_LINK_TYPE, type ProjectLink, type ProjectLinkType } from "../model/schema";`, `useState<ProjectLinkType>(link?.type ?? PROJECT_LINK_TYPE.OTHER)`, `setType(e.target.value as ProjectLinkType)`.
- `modules/projects/index.ts`: `export type { ProjectLink } from "./model/schema";`

- [ ] **Step 4: Run** — `pnpm test && pnpm exec tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** — `fix(projects): validate project fetcher responses with zod schemas`

---

### Task 5: Cloudflare account managers — typed access level and validated fetchers

**Files:**
- Modify: `frontend/src/shared/constants/cloudflare.ts`, `modules/cloudflare-accounts/api/fetchers.ts`, `hooks/use-assign-cloudflare-account-manager.ts`, `hooks/use-update-cloudflare-account-manager.ts`, `ui/cloudflare-account-manager-form-dialog.tsx`, `ui/cloudflare-account-detail-view.tsx`
- Create: `modules/cloudflare-accounts/model/schema.ts`, `modules/cloudflare-accounts/model/schema.test.ts`

**Interfaces:** Produces `ACCESS_LEVEL`/`AccessLevel` (`@/shared/constants/cloudflare`), `cloudflareAccountManagerSchema`/`CloudflareAccountManager`, `revealedTokenSchema` (`modules/cloudflare-accounts/model/schema.ts`).

- [ ] **Step 1: Failing test** — `model/schema.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { cloudflareAccountManagerSchema, revealedTokenSchema } from "./schema";

describe("cloudflare-accounts model schemas", () => {
  it("parses a manager row", () => {
    const parsed = cloudflareAccountManagerSchema.parse({
      userId: "b3f1c2e4-1111-4444-8888-000000000000", email: "a@x.com", name: "A",
      accessLevel: "editor", createdAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed.accessLevel).toBe("editor");
  });

  it("rejects an access level the backend does not define", () => {
    expect(() => cloudflareAccountManagerSchema.parse({
      userId: "b3f1c2e4-1111-4444-8888-000000000000", email: "a@x.com", name: "A",
      accessLevel: "admin", createdAt: "2026-01-01T00:00:00Z",
    })).toThrow();
  });

  it("parses a revealed token", () => {
    expect(revealedTokenSchema.parse({ apiToken: "t" }).apiToken).toBe("t");
  });
});
```

- [ ] **Step 2: Run** — FAIL (module not found).

- [ ] **Step 3: Implement**

`shared/constants/cloudflare.ts` — append:

```ts
export const ACCESS_LEVEL = {
  OWNER: "owner",
  EDITOR: "editor",
  VIEWER: "viewer",
} as const;
export type AccessLevel = (typeof ACCESS_LEVEL)[keyof typeof ACCESS_LEVEL];
```

`modules/cloudflare-accounts/model/schema.ts`:

```ts
import { z } from "zod";
import { ACCESS_LEVEL } from "@/shared/constants/cloudflare";

export const cloudflareAccountManagerSchema = z.object({
  userId: z.uuid(),
  email: z.string(),
  name: z.string(),
  accessLevel: z.enum([ACCESS_LEVEL.OWNER, ACCESS_LEVEL.EDITOR, ACCESS_LEVEL.VIEWER]),
  createdAt: z.string(),
});
export type CloudflareAccountManager = z.infer<typeof cloudflareAccountManagerSchema>;

export const revealedTokenSchema = z.object({ apiToken: z.string() });
```

`api/fetchers.ts`: remove `ACCESS_LEVEL`, `AccessLevel`, `CloudflareAccountManager`; import `cloudflareAccountSchema` from `@/entities/cloudflare-account`, `type AccessLevel` from `@/shared/constants/cloudflare`, and the two schemas above; `createCloudflareAccount`/`updateCloudflareAccount` parse with `cloudflareAccountSchema`, `revealCloudflareAccountToken` returns `revealedTokenSchema.parse(raw).apiToken`, `fetchCloudflareAccountManagers` returns `cloudflareAccountManagerSchema.array().parse(raw)`.

Hooks and manager form dialog: `import { type AccessLevel } from "@/shared/constants/cloudflare"` / `import { ACCESS_LEVEL, type AccessLevel } from "@/shared/constants/cloudflare"`.

`ui/cloudflare-account-detail-view.tsx`:

```tsx
import { ACCESS_LEVEL, type AccessLevel } from "@/shared/constants/cloudflare";
import type { CloudflareAccountManager } from "../model/schema";
...
  const getLevelBadgeStyle = (level: AccessLevel) => {
    switch (level) {
      case ACCESS_LEVEL.OWNER:
        return "border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300";
      case ACCESS_LEVEL.EDITOR:
        return "border-blue-500/40 bg-blue-500/15 text-blue-700 dark:text-blue-300";
      default:
        return "border-border/70 bg-muted/60 text-foreground";
    }
  };
```

(Invoke ui-ux-pro-max before this edit: confirm the blue editor badge keeps AA contrast in both themes.)

- [ ] **Step 4: Run** — `pnpm test && pnpm exec tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** — `fix(cloudflare-accounts): validate manager fetchers and use typed access levels`

---

### Task 6: Validate the project permission set

**Files:**
- Create: `frontend/src/entities/permission/model/schema.ts`, `frontend/src/entities/permission/model/schema.test.ts`
- Modify: `frontend/src/entities/permission/api/fetchers.ts`

**Interfaces:** Produces `projectPermissionSetSchema` / `ProjectPermissionSet`. `fetchProjectPermissions(projectId): Promise<string[]>` unchanged (HIGH-impact symbol — signature must not change).

- [ ] **Step 1: Failing test**

```ts
import { describe, expect, it } from "vitest";
import { projectPermissionSetSchema } from "./schema";

describe("projectPermissionSetSchema", () => {
  it("parses GET /projects/{id}/permissions", () => {
    const parsed = projectPermissionSetSchema.parse({
      projectId: "b3f1c2e4-1111-4444-8888-000000000000",
      permissions: ["project_incident.read", "environment.read"],
    });
    expect(parsed.permissions).toEqual(["project_incident.read", "environment.read"]);
  });

  it("rejects a payload without a permissions array", () => {
    expect(() => projectPermissionSetSchema.parse({ projectId: "b3f1c2e4-1111-4444-8888-000000000000" })).toThrow();
  });
});
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**

```ts
// entities/permission/model/schema.ts
import { z } from "zod";

export const projectPermissionSetSchema = z.object({
  projectId: z.uuid(),
  permissions: z.array(z.string()),
});
export type ProjectPermissionSet = z.infer<typeof projectPermissionSetSchema>;
```

```ts
// entities/permission/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { projectPermissionSetSchema } from "../model/schema";

export async function fetchProjectPermissions(projectId: string): Promise<string[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.PERMISSIONS(projectId));
  return projectPermissionSetSchema.parse(raw).permissions;
}
```

- [ ] **Step 4: Run** — `pnpm test && pnpm exec tsc --noEmit` → PASS (including existing `entities/permission` tests).
- [ ] **Step 5: Commit** — `fix(permission): validate the project permission set response`

---

### Task 7: Tidy the auth module's public surface

**Files:** Modify `frontend/src/modules/auth/model/session.ts`, `modules/auth/index.ts`, `frontend/src/app/[locale]/(dashboard)/dashboard-sidebar.tsx`

- [ ] **Step 1: Implement**

`session.ts`: import only `AUTH_STATUS` (`import { AUTH_STATUS } from "@/shared/constants/auth";`) and delete `export { AUTH_STATUS, type AuthStatus };`.

`index.ts`:

```ts
export { LoginForm } from "./ui/login-form";
export { UserMenu } from "./ui/user-menu";
export { AuthGuard } from "./ui/auth-guard";
export { LanguageSwitch } from "./ui/language-switch";
export { useAuthSession } from "./hooks/use-auth-session";
export { useLogout } from "./hooks/use-logout";
export { fetchAuthSession } from "./api/session";
export { isAuthenticated, type AuthSession, type AuthenticatedAuthSession } from "./model/session";
```

`dashboard-sidebar.tsx`: replace the three deep imports with `import { LanguageSwitch, useAuthSession, useLogout } from "@/modules/auth";`.

- [ ] **Step 2: Verify** — `pnpm exec tsc --noEmit && pnpm lint` → clean (no consumer imported `AUTH_STATUS` via `@/modules/auth`).
- [ ] **Step 3: Commit** — `refactor(auth): drop the AUTH_STATUS re-export and stop deep-importing auth internals`

---

### Task 8: Auth bypass paths and error code from constants

**Files:** Modify `frontend/src/shared/constants/auth.ts`, `shared/constants/api.ts`, `shared/lib/api-client.ts`

- [ ] **Step 1: Implement**

`shared/constants/auth.ts` — append:

```ts
export const AUTH_ERROR_CODE = {
  NOT_AUTHENTICATED: "auth_not_authenticated",
} as const;
```

`shared/constants/api.ts` — inside `ENDPOINTS.AUTH`, add `OAUTH_PREFIX: "/auth/oauth",`.

`shared/lib/api-client.ts`:

```ts
import { AUTH_ERROR_CODE } from "@/shared/constants/auth";
...
const AUTH_BYPASS_PATHS = [
  API_CONFIG.ENDPOINTS.AUTH.REFRESH,
  API_CONFIG.ENDPOINTS.AUTH.OAUTH_PREFIX,
  API_CONFIG.ENDPOINTS.AUTH.LOGOUT,
] as const;

function isAuthBypassUrl(url?: string): boolean {
  if (!url) return false;
  return AUTH_BYPASS_PATHS.some((path) => url.includes(path));
}
...
  const isAuthCode = error.response?.data?.error?.code === AUTH_ERROR_CODE.NOT_AUTHENTICATED;
```

- [ ] **Step 2: Verify** — `pnpm exec tsc --noEmit && pnpm lint && pnpm test` → clean.
- [ ] **Step 3: Commit** — `refactor(api-client): read auth bypass paths and error code from constants`

---

### Task 9: Named icon re-exports

**Files:** Modify `frontend/src/shared/ui/icons/index.ts`

- [ ] **Step 1: Implement**

```ts
export {
  BrandLogo,
  IconAuditLogs,
  IconCloud,
  IconCloudflare,
  IconDashboard,
  IconDns,
  IconGit,
  IconGmail,
  IconGrafana,
  IconJira,
  IconNotification,
  IconPermission,
  IconProject,
  IconServer,
  IconStatus,
  IconTelegram,
  IconUsers,
  type IconProps,
} from "./icons";
```

- [ ] **Step 2: Verify** — `pnpm exec tsc --noEmit` → clean.
- [ ] **Step 3: Commit** — `refactor(icons): replace the export-all barrel with named exports`

---

### Task 10: Type the DNS badge colours

**Files:**
- Modify: `frontend/src/modules/cloudflare-accounts/model/dns.ts`, `ui/account-dns-tab.tsx`, `ui/dns-record-form-dialog.tsx`
- Create: `frontend/src/modules/cloudflare-accounts/model/dns.test.ts`

**Interfaces:** Produces `isDnsType(value: string): value is DnsType`; `DNS_TYPE_COLORS: Record<DnsType, string>`.

- [ ] **Step 1: Failing test**

```ts
import { describe, expect, it } from "vitest";
import { DNS_TYPES, DNS_TYPE_COLORS, isDnsType } from "./dns";

describe("dns model", () => {
  it("has a badge colour for every selectable record type", () => {
    for (const type of DNS_TYPES) {
      expect(DNS_TYPE_COLORS[type]).toBeTruthy();
    }
  });

  it("narrows only known record types", () => {
    expect(isDnsType("HTTPS")).toBe(true);
    expect(isDnsType("PTR")).toBe(false);
  });
});
```

- [ ] **Step 2: Run** — FAIL (`isDnsType` missing, `HTTPS` colour undefined).
- [ ] **Step 3: Implement** (invoke ui-ux-pro-max first to confirm the HTTPS hue is distinct from the existing eight and legible in both themes; default `cyan` with the file's existing 600/400 text shades):

```ts
export const DNS_TYPE_COLORS: Record<DnsType, string> = {
  A: "border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  AAAA: "border-teal-500/30 bg-teal-500/15 text-teal-600 dark:text-teal-400",
  CNAME: "border-blue-500/30 bg-blue-500/15 text-blue-600 dark:text-blue-400",
  MX: "border-purple-500/30 bg-purple-500/15 text-purple-600 dark:text-purple-400",
  TXT: "border-gray-500/30 bg-gray-500/15 text-gray-600 dark:text-gray-400",
  NS: "border-amber-500/30 bg-amber-500/15 text-amber-600 dark:text-amber-400",
  SRV: "border-pink-500/30 bg-pink-500/15 text-pink-600 dark:text-pink-400",
  CAA: "border-red-500/30 bg-red-500/15 text-red-600 dark:text-red-400",
  HTTPS: "border-cyan-500/30 bg-cyan-500/15 text-cyan-600 dark:text-cyan-400",
};

export const isDnsType = (value: string): value is DnsType => (DNS_TYPES as readonly string[]).includes(value);
```

`account-dns-tab.tsx` badge: `const color = isDnsType(type) ? DNS_TYPE_COLORS[type] : "border-border/70 bg-muted/40 text-muted-foreground";` (import `isDnsType`).
`dns-record-form-dialog.tsx`: `value === type ? DNS_TYPE_COLORS[type] : "border-border/60 …"` (drop the `?? "border-primary/50 …"` fallback).

- [ ] **Step 4: Run** — `pnpm test && pnpm exec tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** — `fix(cloudflare-accounts): give every DNS record type a typed badge colour`

---

### Task 11: Translate Cloudflare account tooltips

**Files:** Modify `frontend/src/modules/cloudflare-accounts/ui/cloudflare-account-detail-view.tsx`, `ui/account-dns-tab.tsx`, `frontend/locales/en/modules/cloudflare-accounts.json`, `frontend/locales/vi/modules/cloudflare-accounts.json`

- [ ] **Step 1: Add keys**

| Key | en | vi |
|---|---|---|
| `actions.copyAccountId` | Copy account ID | Sao chép Account ID |
| `actions.copyApiToken` | Copy API token | Sao chép API token |
| `actions.editDnsRecord` | Edit DNS record | Sửa bản ghi DNS |
| `actions.deleteDnsRecord` | Delete DNS record | Xóa bản ghi DNS |
| `managers.remove` | Remove manager | Gỡ người quản lý |

- [ ] **Step 2: Use them** — `title="Click to copy Account ID"` → `title={t("actions.copyAccountId")}`; `title="Copy API Token"` → `title={t("actions.copyApiToken")}`; `title="Remove manager"` → `title={t("managers.remove")}`; in `account-dns-tab.tsx` `title="Edit"` → `title={t("actions.editDnsRecord")}`, `title="Delete"` → `title={t("actions.deleteDnsRecord")}`. (ui-ux-pro-max: icon-only buttons keep an accessible name — add the same key as `aria-label` on the two DNS buttons, which currently have none.)
- [ ] **Step 3: Verify** — `pnpm exec tsc --noEmit && pnpm lint`; `node -e` check both locale files parse and contain the five keys.
- [ ] **Step 4: Commit** — `i18n(cloudflare-accounts): translate account and DNS action tooltips`

---

### Task 12: Move the dashboard body into `modules/dashboard`

**Files:**
- Move: `frontend/src/app/[locale]/(dashboard)/dashboard/page.tsx` → `frontend/src/modules/dashboard/ui/dashboard-view.tsx`
- Create: `frontend/src/modules/dashboard/index.ts`, new `frontend/src/app/[locale]/(dashboard)/dashboard/page.tsx`
- Modify: `frontend/locales/en/common.json`, `frontend/locales/vi/common.json`

**Interfaces:** Produces `DashboardView({ userName, roleName }: { userName?: string | null; roleName?: string | null })`.

- [ ] **Step 1: Move with history** — `git mv "frontend/src/app/[locale]/(dashboard)/dashboard/page.tsx" frontend/src/modules/dashboard/ui/dashboard-view.tsx`
- [ ] **Step 2: Edit the view** — remove `import { useAuthSession } from "@/modules/auth";` and replace the component head:

```tsx
interface DashboardViewProps {
  userName?: string | null;
  roleName?: string | null;
}

export function DashboardView({ userName, roleName }: DashboardViewProps) {
  const tm = useTranslations("common.meta");
  const td = useTranslations("common.dashboard");
  const displayName = userName ?? td("defaultUserName");
  const userRole = (roleName || td("defaultRole")).toUpperCase();
```

and `td("welcomeBack", { name: userName })` → `td("welcomeBack", { name: displayName })`.

- [ ] **Step 3: Public API and thin page**

```ts
// modules/dashboard/index.ts
export { DashboardView } from "./ui/dashboard-view";
```

```tsx
// app/[locale]/(dashboard)/dashboard/page.tsx
"use client";

import { useAuthSession } from "@/modules/auth";
import { DashboardView } from "@/modules/dashboard";

export default function DashboardPage() {
  const { data: session } = useAuthSession();
  return <DashboardView userName={session.user?.name} roleName={session.roleName} />;
}
```

- [ ] **Step 4: Locale keys** — `common.dashboard.defaultUserName`: en "Operator", vi "Người vận hành"; `common.dashboard.defaultRole`: en "Member", vi "Thành viên".
- [ ] **Step 5: Verify** — `pnpm exec tsc --noEmit && pnpm lint` (boundaries: `modules/dashboard` imports only entities/shared).
- [ ] **Step 6: Commit** — `refactor(dashboard): move the dashboard body into modules/dashboard`

---

### Task 13: List every Cloudflare account for manage_all holders

Added after reviewing `app/core/pagination.py` usage: `ListVisibleCloudflareAccounts` reads `accounts.list_page(limit=1000, offset=0)` and drops `total`, so account 1001+ silently disappears (and 1000 exceeds `PaginationDefaults.MAX_PAGE_SIZE`).

**Files:**
- Modify: `backend/app/modules/cloudflare/repository.py` (`AbstractCloudflareAccountRepository`, `CloudflareAccountRepository`), `backend/app/modules/cloudflare/services/list_visible_accounts.py`
- Test: `backend/tests/cloudflare/test_services.py` (`FakeCloudflareAccountRepository`, `TestListVisibleCloudflareAccounts`), `backend/tests/cloudflare/test_repository.py`

**Interfaces:** Produces `AbstractCloudflareAccountRepository.list_all() -> list[CloudflareAccountRead]`.

- [ ] **Step 1: Failing tests**

`tests/cloudflare/test_services.py`, in `TestListVisibleCloudflareAccounts`:

```python
    async def test_manage_all_sees_accounts_beyond_a_single_page(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        for index in range(1001):
            await uow.accounts.create(
                label=f"A{index}", cf_account_id=f"cf-{index}", api_token="x", created_by=ACTOR_ID
            )

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=True)).execute(uuid4())

        assert len(accounts) == 1001
```

`tests/cloudflare/test_repository.py`:

```python
class TestCloudflareAccountRepositoryListAll:
    async def test_returns_every_account_ordered_by_label(self, _session: AsyncSession) -> None:
        repo = CloudflareAccountRepository(_session, CacheClient.__new__(CacheClient))
        for label in ("B", "A", "C"):
            await repo.create(label=label, cf_account_id=f"cf-{label}", api_token="c", created_by=None)

        accounts = await repo.list_all()

        assert [account.label for account in accounts] == ["A", "B", "C"]
```

- [ ] **Step 2: Run** — `uv run pytest tests/cloudflare/test_services.py -k TestListVisibleCloudflareAccounts tests/cloudflare/test_repository.py -k ListAll -q` → FAIL (`1000 != 1001`, `list_all` missing).

- [ ] **Step 3: Implement**

Abstract contract:

```python
    @abstractmethod
    async def list_all(self) -> list[CloudflareAccountRead]:
        """Return every account ordered by label — backs the manage_all view
        of GET /cloudflare-accounts, which is not paginated."""
        raise NotImplementedError
```

Concrete:

```python
    @database
    async def list_all(self) -> list[CloudflareAccountRead]:
        """Return every account ordered by label."""
        rows = await self._session.scalars(select(CloudflareAccount).order_by(CloudflareAccount.label))
        return [CloudflareAccountRead.model_validate(row) for row in rows]
```

Fake (`FakeCloudflareAccountRepository`): `async def list_all(self) -> list[CloudflareAccountRead]: return sorted(self._rows.values(), key=lambda row: row.label)`.

Service — also replace the hardcoded RBAC strings with the rbac facade's constants:

```python
from app.modules.rbac.public import RbacActions, RbacApi, RbacResources
...
        if await self._rbac_api.has_permission(user_id, RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.MANAGE_ALL):
            return await self._uow.accounts.list_all()
```

(and drop the "single generously-sized page" comment).

- [ ] **Step 4: Run** — `uv run pytest tests/cloudflare -q` → PASS.
- [ ] **Step 5: Commit** — `fix(cloudflare): list every account for manage_all holders instead of a 1000-row page`

---

### Task 14: User pickers use the backend page-size bound and the entity fetcher

**Files:**
- Create: `frontend/src/shared/constants/pagination.ts`
- Modify: `frontend/src/modules/cloudflare-accounts/ui/cloudflare-account-manager-form-dialog.tsx`, `frontend/src/modules/projects/ui/project-member-form-dialog.tsx`, `frontend/src/modules/notifications/ui/notification-channel-form-dialog.tsx`

**Interfaces:** Produces `PAGINATION.{DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE}`. Consumes `fetchUsers(limit, offset)` / `useUsers(limit, offset)` from `@/entities/user`.

- [ ] **Step 1: Implement**

```ts
// shared/constants/pagination.ts
/** Mirrors backend app/core/pagination.py PaginationDefaults. */
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 50,
  MAX_PAGE_SIZE: 200,
} as const;
```

Manager dialog: delete the local `UserOption` interface and the `apiFetch`/`API_CONFIG` imports; import `fetchUsers` from `@/entities/user` and `PAGINATION`; the query becomes

```ts
  const { data: users } = useQuery({
    queryKey: userPickerKeys.list(PAGINATION.MAX_PAGE_SIZE),
    queryFn: () => fetchUsers(PAGINATION.MAX_PAGE_SIZE, 0),
  });
```

Member dialog and notification recipients picker: `useUsers(PAGINATION.MAX_PAGE_SIZE, 0)`.

- [ ] **Step 2: Verify** — `pnpm exec tsc --noEmit && pnpm lint && pnpm test` → clean.
- [ ] **Step 3: Commit** — `fix(users): size user pickers by the backend page limit and fetch through the user entity`

**Follow-up (not in this plan):** pickers still stop at `MAX_PAGE_SIZE` users. Fixing that needs a server-side search parameter on `GET /users` and a typeahead picker.

---

### Task 15: Verification and review

- [ ] Backend: `cd backend && uv run ruff check app tests && uv run ruff format --check <changed .py files> && uv run lint-imports && uv run python scripts/check_module_boundaries.py --strict`
- [ ] Backend tests: `uv run pytest tests/projects tests/cloudflare tests/observability tests/notifications tests/users tests/rbac -q`
- [ ] Frontend: `cd frontend && pnpm exec tsc --noEmit && pnpm lint && pnpm test`
- [ ] GitNexus: `node .gitnexus/run.cjs analyze`, then `detect-changes` against `feature/project-scoped-notifications-ui-polish` and `check`; affected symbols must match the Impact Assessment table.
- [ ] reviewing-code-against-skills on the branch diff; fix findings (max 2 architectural rounds).

## Test / Verify Checklist

- [ ] Six compensation tests assert `exc_info` on the first CRITICAL record.
- [ ] Project role list methods issue 2 / 3 statements for three roles.
- [ ] 19 missing-row tests raise the module `*NotFound`.
- [ ] New zod schema tests pass; `tsc`, `eslint` (boundaries, no-cycle) clean.
- [ ] Dashboard, Cloudflare account detail and DNS tab render with translated tooltips in en and vi.
