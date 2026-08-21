# Protected Admin Account Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seed a break-glass admin account from `.env` (`AUTH__ADMIN_EMAIL`) that logs in through the existing DX SSO flow (matched by email) and can never be blocked or have its role reassigned — unconditionally, not contingent on any role count, since `seed_rbac.py` only ever seeds the fixed `admin`/`member` roles (2026-08-21 decision: there is no separate "owner" role anywhere in this system — the protected account is just the `admin` account that must never be lost).

**Architecture:** No schema change. The protection decision (`AuthRules.is_protected_admin_email`) lives entirely in `auth`, which already owns `User.email` and would own the new setting. `rbac`'s `AssignRole` gets a second narrow injected callable (`is_protected: RbacTypes.ProtectionCheck`), mirroring the existing `user_lookup` callable — it never imports `auth.config` or knows about email comparison, matching `scripts/check_module_boundaries.py`'s enforcement. A new idempotent seed script pre-creates the `User` row (with `external_user_id=None`) and grants it the `admin` role — the only elevated role `seed_rbac.py` guarantees exists. When that email later logs in via DX for real, `SyncExternalUser`'s existing "match by email when external_id unseen" fallback links the real identity to the same row automatically — no changes needed to the login flow itself.

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic Settings, pytest — same as the RBAC backend plan this follows.

**Spec:** No separate spec doc — this plan's own Architecture section is the design; it was worked out interactively with the user (2026-08-21) rather than written up as a standalone spec, given the small, well-bounded scope.

## Global Constraints

- Review (ruff check/format, `scripts/check_module_boundaries.py`, manual checklist against `fastapi-modular-scaffold`'s non-negotiable rules) happens **before** every commit, not after — apply the full backend plan's lesson from this same session.
- `scripts/check_module_boundaries.py` (run from `backend/`) is the actual ground truth for cross-module import legality — trust it over any reasoning about whether an import "should" be fine.
- GitNexus MCP tools are not connected this session; manual grep-based impact mapping substitutes for `impact()`/`detect_changes()`.
- No migration in this plan — Approach B (live email comparison) was chosen specifically to avoid one. Do not add a column "for robustness" — that was Approach A, explicitly not chosen.
- `rbac` code must never import `app.modules.auth.config` or compare emails itself — the whole point of `RbacTypes.ProtectionCheck` is that rbac stays ignorant of what "protected" means, it just asks.
- No naming reuses "owner" anywhere — env var, setting, rule, exception, seed script. The RBAC role is `admin`; the break-glass account this plan protects is also referred to as "admin" (the "protected admin account"), never "owner".

---

## Manual impact map (GitNexus substitute)

Grepped 2026-08-21 for every call site that changes shape:

| Symbol | Every reference |
|---|---|
| `AssignRole.__init__` (rbac) | `rbac/services/assign_role.py` (definition), `rbac/public.py`'s `get_assign_role` (constructs it), `tests/rbac/test_services.py`'s `TestAssignRole` (4 test methods construct it directly) |
| `UpdateUserStatus.execute` (auth) | `auth/services/update_user_status.py` (definition), `auth/router.py`'s `update_user_status` route (calls `.execute`), `tests/auth/test_services.py`'s `TestUpdateUserStatus` (3 test methods), `tests/auth/test_router.py`'s `TestUpdateUserStatus` (2 test methods, real HTTP) |
| `AuthApi` (auth/public.py) | `rbac/public.py` (imports `AuthApi`, `get_auth_api`), `auth/router.py` (imports `RbacApi` — unaffected, different class) |

Not touched: `SyncExternalUser`, `AuthenticateWithDx`, migrations, `User` model, `UserRead` schema — confirmed no field changes needed anywhere in this plan.

---

### Task 1: Settings + pure rule

**Files:**
- Modify: `backend/app/modules/auth/config.py`
- Modify: `backend/app/modules/auth/rules.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/auth/test_rules.py`

**Interfaces:**
- Produces: `auth_settings.ADMIN_EMAIL: str | None`, `auth_settings.ADMIN_NAME: str`, `AuthRules.is_protected_admin_email(email: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/auth/test_rules.py`:
```python
from app.modules.auth.config import auth_settings


class TestIsProtectedAdminEmail:
    def test_true_when_email_matches_configured_admin(self, monkeypatch) -> None:
        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", "admin@example.com")
        assert AuthRules.is_protected_admin_email("admin@example.com") is True

    def test_false_when_email_does_not_match(self, monkeypatch) -> None:
        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", "admin@example.com")
        assert AuthRules.is_protected_admin_email("someone-else@example.com") is False

    def test_false_when_admin_email_unset(self, monkeypatch) -> None:
        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", None)
        assert AuthRules.is_protected_admin_email("anyone@example.com") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/auth/test_rules.py::TestIsProtectedAdminEmail -v`
Expected: FAIL — `AttributeError: type object 'AuthConfig' has no attribute 'ADMIN_EMAIL'` (or `AuthRules` has no `is_protected_admin_email`).

- [ ] **Step 3: Add the settings**

In `backend/app/modules/auth/config.py`, add two fields to `AuthConfig`:
```python
    ADMIN_EMAIL: str | None = None
    ADMIN_NAME: str = "Admin"
```
(placed after `COOKIE_SECURE: bool = True`, before the `cookie_domain` property)

- [ ] **Step 4: Add the rule**

In `backend/app/modules/auth/rules.py`, add to `AuthRules` (after `can_login`):
```python
    @staticmethod
    @rule
    def is_protected_admin_email(email: str) -> bool:
        """True when email matches the seeded break-glass admin account
        (AUTH__ADMIN_EMAIL) — that account can never be blocked or have its
        role reassigned, regardless of how many other admins exist."""
        return bool(auth_settings.ADMIN_EMAIL) and email == auth_settings.ADMIN_EMAIL
```
Add the import at the top: `from app.modules.auth.config import auth_settings`.

- [ ] **Step 5: Document the env vars**

Add to `backend/.env.example`, after `AUTH__COOKIE_SECURE=false`:
```
AUTH__ADMIN_EMAIL=
AUTH__ADMIN_NAME=Admin
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/auth/test_rules.py -v`
Expected: PASS (all tests, including the 3 new ones — `monkeypatch` is a built-in pytest fixture, no new dependency).

- [ ] **Step 7: `ruff check` + `ruff format --check`**

Run: `uv run ruff check app/modules/auth/config.py app/modules/auth/rules.py tests/auth/test_rules.py && uv run ruff format --check app/modules/auth/config.py app/modules/auth/rules.py tests/auth/test_rules.py`
Expected: `All checks passed!` / files already formatted

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/auth/config.py backend/app/modules/auth/rules.py backend/.env.example backend/tests/auth/test_rules.py
git commit -m "feat(auth): AUTH__ADMIN_EMAIL setting and is_protected_admin_email rule"
```

---

### Task 2: Exceptions + facade method

**Files:**
- Modify: `backend/app/modules/auth/constants.py`
- Modify: `backend/app/modules/auth/exceptions.py`
- Modify: `backend/app/modules/auth/public.py`
- Modify: `backend/app/modules/rbac/constants.py`
- Modify: `backend/app/modules/rbac/exceptions.py`

**Interfaces:**
- Consumes: `AuthRules.is_protected_admin_email` (Task 1).
- Produces: `AuthApi.is_protected_admin(user_id: int) -> bool`; `auth.exceptions.CannotModifyProtectedAdmin`; `rbac.exceptions.CannotModifyProtectedAdmin`; `RbacTypes.ProtectionCheck` type alias.

No new test file for this task — `AuthApi.is_protected_admin` is exercised end-to-end by Task 3's/Task 4's tests, matching how `get_user_by_id` had no dedicated test either (composition-root/facade functions are covered by their consumers).

- [ ] **Step 1: `auth/constants.py`** — add to `ErrorCode`:
```python
    CANNOT_MODIFY_PROTECTED_ADMIN = "auth_cannot_modify_protected_admin"
```
(alongside the existing `CANNOT_BLOCK_LAST_ADMIN`)

- [ ] **Step 2: `auth/exceptions.py`** — add:
```python
class CannotModifyProtectedAdmin(ForbiddenError):
    """Raised when attempting to block the seeded break-glass admin account."""

    code = ErrorCode.CANNOT_MODIFY_PROTECTED_ADMIN
    message = "This account is permanently protected and cannot be blocked"
```
(alongside `CannotBlockLastAdmin`)

- [ ] **Step 3: `auth/public.py`** — add the facade method:
```python
    @facade
    async def is_protected_admin(self, user_id: int) -> bool:
        """True when user_id is the seeded break-glass admin account —
        used by rbac's AssignRole to reject reassigning its role."""
        user = await self.get_user_by_id(user_id)
        return user is not None and AuthRules.is_protected_admin_email(user.email)
```
Add the import: `from app.modules.auth.rules import AuthRules`.

- [ ] **Step 4: `rbac/constants.py`** — extend `RbacTypes` and `ErrorCode`:
```python
class RbacTypes:
    """Type aliases owned by the rbac module."""

    UserLookup = Callable[[int], Awaitable[Any | None]]
    ProtectionCheck = Callable[[int], Awaitable[bool]]
```
Add to `ErrorCode`:
```python
    CANNOT_MODIFY_PROTECTED_ADMIN = "rbac_cannot_modify_protected_admin"
```

- [ ] **Step 5: `rbac/exceptions.py`** — add:
```python
class CannotModifyProtectedAdmin(ForbiddenError):
    """Raised when attempting to reassign the role of the seeded break-glass
    admin account — its role is permanently locked."""

    code = ErrorCode.CANNOT_MODIFY_PROTECTED_ADMIN
    message = "This account's role is permanently locked and cannot be changed"
```

- [ ] **Step 6: Verify it imports cleanly**

Run: `cd backend && uv run python -c "from app.modules.auth.public import AuthApi; from app.modules.rbac.constants import RbacTypes; from app.modules.rbac.exceptions import CannotModifyProtectedAdmin as RbacCMPA; from app.modules.auth.exceptions import CannotModifyProtectedAdmin as AuthCMPA; print('ok')"`
Expected: `ok`

- [ ] **Step 7: `ruff check` + `ruff format --check` + boundary check**

Run: `uv run ruff check app/modules/auth app/modules/rbac && uv run ruff format --check app/modules/auth app/modules/rbac && python3 scripts/check_module_boundaries.py`
Expected: all clean

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/auth/constants.py backend/app/modules/auth/exceptions.py backend/app/modules/auth/public.py backend/app/modules/rbac/constants.py backend/app/modules/rbac/exceptions.py
git commit -m "feat(auth,rbac): CannotModifyProtectedAdmin exceptions and AuthApi.is_protected_admin facade"
```

---

### Task 3: Wire into `UpdateUserStatus` (auth)

**Files:**
- Modify: `backend/app/modules/auth/services/update_user_status.py`
- Test: `backend/tests/auth/test_services.py`
- Test: `backend/tests/auth/test_router.py`

**Interfaces:**
- Consumes: `AuthRules.is_protected_admin_email` (Task 1).
- Produces: `UpdateUserStatus.execute` now raises `CannotModifyProtectedAdmin` before the existing `CannotBlockLastAdmin` check.

- [ ] **Step 1: Write the failing unit test**

Add to `backend/tests/auth/test_services.py`'s `TestUpdateUserStatus` class:
```python
    async def test_rejects_blocking_the_protected_admin(self, monkeypatch) -> None:
        from app.modules.auth.config import auth_settings

        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", "protected@example.com")
        uow = FakeAuthUnitOfWork()
        user = await uow.users.create(
            email="protected@example.com",
            name="Protected",
            external_user_id="dx-protected",
            employee_code=None,
            email_confirmed=True,
        )
        rbac_api = FakeRbacApi()  # is_last_admin would return False — protection must win regardless

        with pytest.raises(CannotModifyProtectedAdmin):
            await UpdateUserStatus(uow, rbac_api).execute(user.id, UserStatus.BLOCKED)

        assert uow.commits == 0
```
Add the import: `from app.modules.auth.exceptions import CannotBlockLastAdmin, CannotModifyProtectedAdmin, UserBlocked` (extends the existing import line, replacing the current `CannotBlockLastAdmin, UserBlocked` names).

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/auth/test_services.py::TestUpdateUserStatus::test_rejects_blocking_the_protected_admin -v`
Expected: FAIL — the exception isn't raised yet, `CannotModifyProtectedAdmin` isn't even importable from `update_user_status`'s module namespace in the test (import error first, then assertion failure once fixed).

- [ ] **Step 3: Implement**

Rewrite `backend/app/modules/auth/services/update_user_status.py`:
```python
"""Use case: block or unblock a user."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.auth.constants import UserStatus
from app.modules.auth.exceptions import CannotBlockLastAdmin, CannotModifyProtectedAdmin
from app.modules.auth.rules import AuthRules
from app.modules.auth.schemas import UserRead
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.rbac.public import RbacApi


class UpdateUserStatus(AbstractUseCase):
    """Block or unblock a user. Two independent rejections apply only when
    blocking: the seeded break-glass admin account is always protected
    (checked first, unconditional on admin count); the last admin is
    protected as long as no break-glass account exists to fall back on
    (rbac's own bus-factor rule, mirroring AssignRole for the analogous
    role-reassignment case)."""

    def __init__(self, uow: AbstractAuthUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, user_id: int, status: UserStatus) -> UserRead:
        if status == UserStatus.BLOCKED:
            target = await self._uow.users.get_by_id(user_id)
            if target is not None and AuthRules.is_protected_admin_email(target.email):
                raise CannotModifyProtectedAdmin()
            if await self._rbac_api.is_last_admin(user_id):
                raise CannotBlockLastAdmin()
        updated = await self._uow.users.set_status(user_id, status)
        await self._uow.commit()
        return updated
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/auth/test_services.py -v`
Expected: PASS, all `TestUpdateUserStatus` tests including the new one.

- [ ] **Step 5: Add the router-level integration test**

Add to `backend/tests/auth/test_router.py`'s `TestUpdateUserStatus` class:
```python
    async def test_rejects_blocking_the_protected_admin(
        self, client: AsyncClient, engine: AsyncEngine, monkeypatch
    ) -> None:
        from app.modules.auth.config import auth_settings

        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", "protected-router@example.com")
        await _login_with_permissions(client, engine, permissions=[("user", "update_status")])
        async with engine.begin() as conn:
            target = await conn.execute(
                insert(User).values(
                    email="protected-router@example.com",
                    name="Protected",
                    status="active",
                    external_user_id="dx-protected-router",
                    employee_code=None,
                    email_confirmed=True,
                )
            )
            target_id = target.inserted_primary_key[0]

        response = await client.patch(f"/api/v1/auth/users/{target_id}/status", json={"status": "blocked"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "auth_cannot_modify_protected_admin"
```

- [ ] **Step 6: Run the full auth test suite**

Run: `uv run pytest tests/auth -v`
Expected: PASS, all files.

- [ ] **Step 7: `ruff check` + `ruff format --check`**

Run: `uv run ruff check app/modules/auth tests/auth && uv run ruff format --check app/modules/auth tests/auth`
Expected: clean

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/auth/services/update_user_status.py backend/tests/auth/test_services.py backend/tests/auth/test_router.py
git commit -m "feat(auth): reject blocking the protected admin account"
```

---

### Task 4: Wire into `AssignRole` (rbac)

**Files:**
- Modify: `backend/app/modules/rbac/services/assign_role.py`
- Modify: `backend/app/modules/rbac/public.py`
- Test: `backend/tests/rbac/test_services.py`
- Test: `backend/tests/rbac/test_router.py`

**Interfaces:**
- Consumes: `AuthApi.is_protected_admin` (Task 2), `RbacTypes.ProtectionCheck` (Task 2).
- Produces: `AssignRole.__init__` gains a required `is_protected: RbacTypes.ProtectionCheck` parameter.

- [ ] **Step 1: Update the existing failing calls first**

In `backend/tests/rbac/test_services.py`'s `TestAssignRole`, every `AssignRole(uow, user_lookup)` call needs a third argument. Add a shared fake at module scope (near `_admin_role`):
```python
async def _not_protected(user_id: int) -> bool:
    return False
```
Then update all 4 existing `TestAssignRole` methods' `AssignRole(uow, user_lookup)` calls to `AssignRole(uow, user_lookup, _not_protected)`.

- [ ] **Step 2: Write the new failing test**

Add to `TestAssignRole`:
```python
    async def test_rejects_modifying_a_protected_admin(self) -> None:
        uow = FakeRbacUnitOfWork()
        uow.roles.seed(RoleRead(id=1, name="support", is_system=False, permissions=[]))

        async def user_lookup(user_id: int):
            return object()

        async def is_protected(user_id: int) -> bool:
            return True

        with pytest.raises(CannotModifyProtectedAdmin):
            await AssignRole(uow, user_lookup, is_protected).execute(42, 1)

        assert 42 not in uow.user_roles.grants
```
Add the import: `from app.modules.rbac.exceptions import CannotModifyProtectedAdmin` (extend the existing multi-name import from `app.modules.rbac.exceptions`).

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && uv run pytest tests/rbac/test_services.py -v`
Expected: FAIL — `AssignRole.__init__() missing 1 required positional argument: 'is_protected'` on every `TestAssignRole` test (all 5, including the new one), since the Fakes are already updated to pass 3 args but the real class only accepts 2 yet.

- [ ] **Step 4: Implement**

Rewrite `backend/app/modules/rbac/services/assign_role.py`:
```python
"""Use case: assign a role to an existing user (admin action)."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.constants import RbacTypes
from app.modules.rbac.exceptions import (
    CannotModifyProtectedAdmin,
    CannotRemoveLastAdmin,
    RoleNotFound,
    TargetUserNotFound,
)
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.uow import AbstractRbacUnitOfWork


class AssignRole(AbstractUseCase):
    """user_lookup and is_protected are both injected rather than importing
    auth directly, so this service depends only on two narrow capabilities —
    dependencies wired in rbac/public.py's get_assign_role to
    app.modules.auth.public.AuthApi.get_user_by_id / .is_protected_admin."""

    def __init__(
        self,
        uow: AbstractRbacUnitOfWork,
        user_lookup: RbacTypes.UserLookup,
        is_protected: RbacTypes.ProtectionCheck,
    ) -> None:
        self._uow = uow
        self._user_lookup = user_lookup
        self._is_protected = is_protected

    @use_case
    async def execute(self, user_id: int, role_id: int) -> None:
        if await self._user_lookup(user_id) is None:
            raise TargetUserNotFound()
        if await self._is_protected(user_id):
            raise CannotModifyProtectedAdmin()
        role = await self._uow.roles.get_by_id(role_id)
        if role is None:
            raise RoleNotFound()

        current = await self._uow.user_roles.get_role_for_user(user_id)
        if current is not None:
            admin_grants = await self._uow.roles.count_users_with_role(current.id)
            if RbacRules.blocks_last_admin_removal(current.name, admin_grants):
                raise CannotRemoveLastAdmin()

        await self._uow.user_roles.assign(user_id, role_id)
        await self._uow.commit()
```

- [ ] **Step 5: Wire the facade**

In `backend/app/modules/rbac/public.py`, update `get_assign_role`:
```python
async def get_assign_role(
    uow: AbstractRbacUnitOfWork = Depends(get_uow),
    auth_api: AuthApi = Depends(get_auth_api),
) -> AssignRole:
    """Provide the assign-role use case, wired to auth's user-existence and
    protected-admin checks."""
    return AssignRole(uow, auth_api.get_user_by_id, auth_api.is_protected_admin)
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/rbac/test_services.py -v`
Expected: PASS, all `TestAssignRole` tests (5, including the new one) plus every other test in the file.

- [ ] **Step 7: Add the router-level integration test**

Add to `backend/tests/rbac/test_router.py`'s `TestAssignUserRole` class:
```python
    async def test_rejects_reassigning_the_protected_admin(
        self, client: AsyncClient, engine: AsyncEngine, monkeypatch
    ) -> None:
        from app.modules.auth.config import auth_settings

        monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", "protected-rbac@example.com")
        await _login_as(client, engine, permissions=[("user", "assign_role")])
        role_id = await _seed_role(engine, "viewer3", is_system=False, permission_ids=[])
        target_user_id = await _seed_user(
            engine, email="protected-rbac@example.com", external_user_id="dx-protected-rbac"
        )

        response = await client.patch(f"/api/v1/rbac/users/{target_user_id}/role", json={"roleId": role_id})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_cannot_modify_protected_admin"
```

- [ ] **Step 8: Run the full rbac test suite**

Run: `uv run pytest tests/rbac -v`
Expected: PASS, all files.

- [ ] **Step 9: `ruff check` + `ruff format --check` + boundary check**

Run: `uv run ruff check app/modules/rbac tests/rbac && uv run ruff format --check app/modules/rbac tests/rbac && python3 scripts/check_module_boundaries.py`
Expected: all clean

- [ ] **Step 10: Commit**

```bash
git add backend/app/modules/rbac/services/assign_role.py backend/app/modules/rbac/public.py backend/tests/rbac/test_services.py backend/tests/rbac/test_router.py
git commit -m "feat(rbac): reject reassigning the protected admin's role"
```

---

### Task 5: Seed script

**Files:**
- Create: `backend/app/seeds/seed_admin.py`

**Interfaces:**
- Consumes: `auth_settings.ADMIN_EMAIL`/`ADMIN_NAME` (Task 1), `RbacDefaults.ADMIN_ROLE_NAME` (existing — `seed_rbac.py` guarantees this one exists).
- Produces: idempotent `python -m app.seeds.seed_admin`.

No unit test — matches `seed_rbac.py`'s own convention (schema/data-seeding scripts are verified by running them against the real DB, not by a pytest suite; the fastapi-modular-scaffold checklist's "no module without a test folder" rule targets `app/modules/`, not `app/seeds/`).

- [ ] **Step 1: Write the seed script**

```python
"""Idempotent seed: the break-glass admin account from AUTH__ADMIN_EMAIL.

Run via `python -m app.seeds.seed_admin`. No-op (with a log line) if
AUTH__ADMIN_EMAIL is unset — this is an optional bootstrap step, not a
requirement to run the app. Requires seed_rbac.py to have already run (the
admin role must exist). This account's protection (see
AuthRules.is_protected_admin_email) is by email, not by holding any
particular role — the admin role grant just gives it the same full access
every admin has, nothing more.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import UserStatus
from app.modules.auth.models import User
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.models import Role, UserRole

logger = logging.getLogger(__name__)


async def run() -> None:
    """Upsert the break-glass admin user and grant it the admin role."""
    if not auth_settings.ADMIN_EMAIL:
        logger.info("AUTH__ADMIN_EMAIL not set — skipping admin seed")
        return

    engine = create_async_engine(str(settings.DATABASE_URL))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == auth_settings.ADMIN_EMAIL))
        if user is None:
            user = User(
                email=auth_settings.ADMIN_EMAIL,
                name=auth_settings.ADMIN_NAME,
                status=UserStatus.ACTIVE,
                external_user_id=None,
                employee_code=None,
                email_confirmed=True,
            )
            session.add(user)
            await session.flush()
            logger.info("seeded break-glass admin user %s", auth_settings.ADMIN_EMAIL)

        admin_role = await session.scalar(select(Role).where(Role.name == RbacDefaults.ADMIN_ROLE_NAME))
        if admin_role is None:
            raise RuntimeError("admin role missing — run `python -m app.seeds.seed_rbac` first")

        grant = await session.get(UserRole, user.id)
        if grant is None:
            session.add(UserRole(user_id=user.id, role_id=admin_role.id))
            logger.info("granted admin role to %s", auth_settings.ADMIN_EMAIL)
        elif grant.role_id != admin_role.id:
            grant.role_id = admin_role.id
            logger.info("reasserted admin role for %s", auth_settings.ADMIN_EMAIL)

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 2: `ruff check` + `ruff format --check`**

Run: `cd backend && uv run ruff check app/seeds/seed_admin.py && uv run ruff format --check app/seeds/seed_admin.py`
Expected: clean

- [ ] **Step 3: Run it against the real local DB with `AUTH__ADMIN_EMAIL` unset — verify the no-op path**

Run: `uv run python -m app.seeds.seed_admin`
Expected: logs "AUTH__ADMIN_EMAIL not set — skipping admin seed", exits 0, no DB rows created (`SELECT COUNT(*) FROM users` unchanged).

- [ ] **Step 4: Set `AUTH__ADMIN_EMAIL` and run it for real**

Run: `AUTH__ADMIN_EMAIL=admin@example.com AUTH__ADMIN_NAME="Example Admin" uv run python -m app.seeds.seed_admin`
Expected: logs "seeded break-glass admin user admin@example.com" and "granted admin role to admin@example.com". Verify: `psql ... -c "select u.email, u.external_user_id, r.name from users u join user_roles ur on ur.user_id=u.id join roles r on r.id=ur.role_id where u.email='admin@example.com'"` shows one row, `external_user_id` is NULL, role is `admin`.

- [ ] **Step 5: Run it again — verify idempotency**

Run: `AUTH__ADMIN_EMAIL=admin@example.com uv run python -m app.seeds.seed_admin`
Expected: no "seeded"/"granted" log lines (both branches already satisfied), `SELECT COUNT(*) FROM users WHERE email='admin@example.com'` still returns 1.

- [ ] **Step 6: Clean up the manual test row**

Run: `psql ... -c "delete from user_roles where user_id in (select id from users where email='admin@example.com'); delete from users where email='admin@example.com';"`
(Leaves the local DB in the same state Task 5 started with — this row was created purely to verify the script, not as a fixture for later tasks.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/seeds/seed_admin.py
git commit -m "feat(auth): idempotent seed script for the break-glass admin account"
```

---

## Self-review notes

- **Spec coverage:** DX-SSO-only login preserved (no new code touches `SyncExternalUser`/`AuthenticateWithDx` — the existing email-fallback matching does the linking); absolute protection (both block and role-reassignment paths reject unconditionally, not just at the last-admin boundary); no new column (Approach B honored throughout — grep confirms no migration file in this plan). All three original asks covered.
- **Placeholder scan:** no TODO/TBD; every step has real code.
- **Type consistency:** `RbacTypes.ProtectionCheck` defined once (Task 2), consumed with the identical signature in Task 4's `AssignRole.__init__` and `rbac/public.py`'s `get_assign_role`. `AuthApi.is_protected_admin`'s name and signature match across Task 2 (definition) and Task 4 (consumption in `get_assign_role`).
- One deliberate omission, called out rather than silently skipped: this plan does **not** add a `GET /auth/users` response field indicating "this user is protected" — the frontend would need that to grey out the block/reassign controls (per this project's own `rbac-ui.md`: UX should reflect what the backend will actually reject). Left for the frontend plan, since `MeResponse`/`UserRead`-shaped responses and their frontend consumption are that plan's territory, not this backend-only one.
- **Naming note:** the "protected admin account" (this plan, singular break-glass account, identified by email) and "the admin role" (RBAC, `RbacDefaults.ADMIN_ROLE_NAME`, potentially held by several users) both use the word "admin" deliberately — there is no more "owner" concept anywhere in this system. Prose throughout this plan says "protected admin account" (never bare "admin") when referring to the former, to keep the two readable apart.

## Execution note

Task 4 Step 1 deliberately updates the *test* fakes' call sites before the real class accepts the new parameter — this is the TDD "fail for the right reason" step: running the suite at that point should fail with a `TypeError` on argument count, not an import error, confirming the test changes are wired correctly before touching the implementation.
