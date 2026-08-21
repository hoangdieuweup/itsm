# Users Module Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split user administration out of `auth` into a new `users` module. `auth` is left owning only session/SSO concerns; `users` owns the `User` entity, its CRUD, and the protected-admin-account rules. No database migration — same `users` table, same columns, just a different owning Python module.

**Architecture:** See `docs/superpowers/specs/2026-08-21-users-module-split-design.md` for the full design — module boundary, the 3-way `auth → users → rbac → auth` circular-dependency shape and why it's actually safe with careful factory placement, and the transaction/cache-invalidation ownership fix (`UsersApi.invalidate_user`) for writes `auth`'s login flow makes into `users`' table.

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic Settings, pytest — same as the rest of this backend.

**Spec:** `docs/superpowers/specs/2026-08-21-users-module-split-design.md`

## Global Constraints

- Review (ruff check/format, `scripts/check_module_boundaries.py`, manual checklist) happens **before** every commit, not after.
- `scripts/check_module_boundaries.py` (run from `backend/`) is the ground truth for cross-module import legality — after each task that touches cross-module imports, run it and a real `python -c "from app.main import app"` to catch a load-time circular import, not just reasoning about it.
- No `# noqa`/local imports to route around a cycle — if one appears, the fix is moving the composition factory to a leaf `router.py`, per the precedent this session already established once between `auth` and `rbac` (see `auth/router.py`'s and `rbac/public.py`'s docstrings).
- `AUTH__ADMIN_EMAIL`/`AUTH__ADMIN_NAME` become `USERS__ADMIN_EMAIL`/`USERS__ADMIN_NAME` — this repo's local `.env` already has a real value seeded under the old name (`hoangvandieu.weup@gmail.com`) that Task 1 must carry over, not drop.
- Error codes `auth_user_not_found`, `auth_cannot_block_last_admin`, `auth_cannot_modify_protected_admin` become `users_user_not_found`, `users_cannot_block_last_admin`, `users_cannot_modify_protected_admin` — a breaking change for the frontend's i18n error-code mapping, called out again in Task 7's checklist.
- API prefix for user administration moves from `/api/v1/auth/users` to `/api/v1/users`.

---

## Manual impact map (GitNexus substitute — GitNexus MCP not connected this session)

Grepped 2026-08-21 for every symbol that changes shape or owning module:

| Symbol | Every reference |
|---|---|
| `User` model | `app/modules/auth/models.py` (definition, moves), `app/seeds/seed_admin.py` (imports it), `tests/rbac/test_router.py` (imports it) |
| `UserRead`/`UserStatusUpdate` schemas | `auth/schemas.py` (definition, moves), `auth/public.py`, `rbac/public.py`, `rbac/router.py` (import `UserRead` from `auth.public`) |
| `AuthApi.get_user_by_id` | `rbac/public.py`'s `get_assign_role` (only caller — replaced by `UsersApi.get_user_by_id`) |
| `AuthApi.is_protected_admin` | same — replaced by `UsersApi.is_protected_admin` |
| `UpdateUserStatus` (auth) | `auth/services/update_user_status.py` (definition, moves), `auth/router.py`'s `update_user_status` route (moves with it), `tests/auth/test_services.py`, `tests/auth/test_router.py` |
| `AuthConfig.ADMIN_EMAIL`/`ADMIN_NAME` | `auth/config.py` (moves), `app/seeds/seed_admin.py`, `.env`, `.env.example`, `tests/auth/test_services.py`, `tests/auth/test_router.py`, `tests/rbac/test_router.py` (all monkeypatch this) |
| `AuthRules.is_protected_admin_email` | `auth/rules.py` (moves), `auth/services/update_user_status.py` (moves with the use case), `tests/auth/test_rules.py` |
| `CannotBlockLastAdmin`/`CannotModifyProtectedAdmin` (auth) | `auth/exceptions.py` (moves), `auth/services/update_user_status.py` (moves with it), `tests/auth/test_services.py`, `tests/auth/test_router.py` |
| `UserCreated` event | `auth/events.py` (moves), `auth/services/authenticate.py` (publisher, stays but imports from `users.public`) |
| `SyncExternalUser` | owns no table itself but constructs off `AbstractAuthUnitOfWork` today — constructor changes to take `UsersApi` |
| `AuthenticateWithDx` | gains a `users_api: UsersApi` constructor param |
| `AbstractAuthUnitOfWork`/`AuthUnitOfWork` | loses `users` repository attribute entirely — becomes a bare transaction coordinator |
| `get_current_user` (auth/dependencies.py) | resolves via `UsersApi.get_user_by_id` instead of `uow.users.get_by_id` |

Not touched: rbac's own tables/migrations, the permission catalog (`resource="user"` stays as a business-concept name, unrelated to the Python module boundary), frontend beyond what Task 7 flags.

---

### Task 1: Scaffold `users` — config, constants, exceptions, models, schemas, rules

**Files:**
- Create: `backend/app/modules/users/__init__.py` (empty)
- Create: `backend/app/modules/users/config.py`
- Create: `backend/app/modules/users/constants.py`
- Create: `backend/app/modules/users/exceptions.py`
- Create: `backend/app/modules/users/models.py`
- Create: `backend/app/modules/users/schemas.py`
- Create: `backend/app/modules/users/rules.py`
- Modify: `backend/.env`, `backend/.env.example`
- Test: `backend/tests/users/__init__.py` (empty), `backend/tests/users/test_rules.py`

**Interfaces:**
- Produces: `users_settings.ADMIN_EMAIL: str | None`, `users_settings.ADMIN_NAME: str`, `UserStatus`, `UserLimits`, `UsersEvents`, `UsersCacheKeys`, `ErrorCode.{USER_NOT_FOUND,CANNOT_BLOCK_LAST_ADMIN,CANNOT_MODIFY_PROTECTED_ADMIN}`, `UserNotFound`, `CannotBlockLastAdmin`, `CannotModifyProtectedAdmin`, `User` (ORM), `UserRead`, `UserStatusUpdate`, `UsersRules.is_protected_admin_email`.

- [ ] **Step 1: `backend/app/modules/users/config.py`**
```python
"""Settings owned by the users module."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class UsersConfig(BaseSettings):
    """Environment driven settings for the users module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="USERS__", extra="ignore")

    ADMIN_EMAIL: str | None = None
    ADMIN_NAME: str = "Admin"


users_settings = UsersConfig()
```

- [ ] **Step 2: `backend/app/modules/users/constants.py`**
```python
"""Constants and enums owned by the users module."""

from enum import StrEnum


class UserStatus(StrEnum):
    """Lifecycle state of a user account."""

    ACTIVE = "active"
    PENDING = "pending"
    BLOCKED = "blocked"


class UserLimits:
    """Numeric limits owned by the users module."""

    MAX_NAME_LENGTH = 255
    MAX_EMAIL_LENGTH = 320
    MAX_EMPLOYEE_CODE_LENGTH = 64
    DEFAULT_PAGE_SIZE = 50


class UsersEvents:
    """Messaging identity owned by the users module. See references/messaging.md."""

    EXCHANGE = "users"


class UsersCacheKeys:
    """Cache identity owned by the users module. See references/caching.md.

    ENTITY stays "user" (not "users") — it's the Redis key prefix, already
    live from the auth-module caching work; renaming it would just orphan
    warm cache entries for no benefit.
    """

    ENTITY = "user"
    TTL_SECONDS = 300


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    USER_NOT_FOUND = "users_user_not_found"
    CANNOT_BLOCK_LAST_ADMIN = "users_cannot_block_last_admin"
    CANNOT_MODIFY_PROTECTED_ADMIN = "users_cannot_modify_protected_admin"
```

- [ ] **Step 3: `backend/app/modules/users/exceptions.py`**
```python
"""Errors owned by the users module."""

from app.core.exceptions import ForbiddenError, NotFoundError
from app.modules.users.constants import ErrorCode


class UserNotFound(NotFoundError):
    """Raised when no user matches the requested identifier."""

    code = ErrorCode.USER_NOT_FOUND
    message = "User not found"


class CannotBlockLastAdmin(ForbiddenError):
    """Raised when blocking this user would leave zero users holding the admin role."""

    code = ErrorCode.CANNOT_BLOCK_LAST_ADMIN
    message = "This is the last user with the admin role — reassign it before blocking them"


class CannotModifyProtectedAdmin(ForbiddenError):
    """Raised when attempting to block the seeded break-glass admin account."""

    code = ErrorCode.CANNOT_MODIFY_PROTECTED_ADMIN
    message = "This account is permanently protected and cannot be blocked"
```

- [ ] **Step 4: `backend/app/modules/users/models.py`**
```python
"""ORM models owned by the users module. No other module may query these tables."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.users.constants import UserLimits, UserStatus


class User(Base):
    """A user account, synced from a DX profile on every successful login."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(UserLimits.MAX_EMAIL_LENGTH), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(UserLimits.MAX_NAME_LENGTH))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False), default=UserStatus.PENDING, index=True
    )
    external_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    employee_code: Mapped[str | None] = mapped_column(
        String(UserLimits.MAX_EMPLOYEE_CODE_LENGTH), nullable=True
    )
    email_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```
Same table name, same columns as the current `auth/models.py:User` — Alembic will detect zero schema diff. Do not create a migration for this task.

- [ ] **Step 5: `backend/app/modules/users/schemas.py`**
```python
"""Schemas for the users module."""

from datetime import datetime

from app.core.models import FrozenModel
from app.modules.users.constants import UserStatus


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


class UserStatusUpdate(FrozenModel):
    """Request body for PATCH /users/{id}/status."""

    status: UserStatus
```

- [ ] **Step 6: `backend/app/modules/users/rules.py`**
```python
"""Business rules for the users module.

Everything here is a pure decision: no I/O, no framework, no database.
"""

from app.core.base.markers import rule
from app.modules.users.config import users_settings


class UsersRules:
    """Every business decision about a user account."""

    @staticmethod
    @rule
    def is_protected_admin_email(email: str) -> bool:
        """True when email matches the seeded break-glass admin account
        (USERS__ADMIN_EMAIL) — that account can never be blocked or have its
        role reassigned, regardless of how many other admins exist."""
        return bool(users_settings.ADMIN_EMAIL) and email == users_settings.ADMIN_EMAIL
```

- [ ] **Step 7: rename the env var**

In `backend/.env`, replace:
```
AUTH__ADMIN_EMAIL=hoangvandieu.weup@gmail.com
AUTH__ADMIN_NAME=Admin
```
with:
```
USERS__ADMIN_EMAIL=hoangvandieu.weup@gmail.com
USERS__ADMIN_NAME=Admin
```

In `backend/.env.example`, replace:
```
AUTH__ADMIN_EMAIL=
AUTH__ADMIN_NAME=Admin
```
with:
```
USERS__ADMIN_EMAIL=
USERS__ADMIN_NAME=Admin
```

- [ ] **Step 8: move the rule's test**

Create `backend/tests/users/__init__.py` (empty) and `backend/tests/users/test_rules.py`:
```python
"""Unit tests for app.modules.users.rules — pure decisions, no I/O, no fixtures."""

import pytest

from app.modules.users.config import users_settings
from app.modules.users.rules import UsersRules


class TestIsProtectedAdminEmail:
    def test_true_when_email_matches_configured_admin(self, monkeypatch) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", "admin@example.com")
        assert UsersRules.is_protected_admin_email("admin@example.com") is True

    def test_false_when_email_does_not_match(self, monkeypatch) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", "admin@example.com")
        assert UsersRules.is_protected_admin_email("someone-else@example.com") is False

    def test_false_when_admin_email_unset(self, monkeypatch) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", None)
        assert UsersRules.is_protected_admin_email("anyone@example.com") is False
```
(Leave `backend/tests/auth/test_rules.py`'s copy of these tests in place for now — Task 6 removes it once auth's own `is_protected_admin_email` is gone.)

- [ ] **Step 9: verify it imports cleanly and tests pass**

Run: `cd backend && uv run python -c "from app.modules.users.models import User; from app.modules.users.schemas import UserRead; from app.modules.users.exceptions import UserNotFound; print('ok')"`
Expected: `ok`

Run: `uv run pytest tests/users -v`
Expected: 3 passed.

- [ ] **Step 10: `ruff check` + `ruff format --check`**

Run: `uv run ruff check app/modules/users tests/users && uv run ruff format --check app/modules/users tests/users`
Expected: clean

- [ ] **Step 11: Commit**
```bash
git add backend/app/modules/users/__init__.py backend/app/modules/users/config.py backend/app/modules/users/constants.py backend/app/modules/users/exceptions.py backend/app/modules/users/models.py backend/app/modules/users/schemas.py backend/app/modules/users/rules.py backend/.env.example backend/tests/users/
git commit -m "feat(users): scaffold module — config, constants, exceptions, models, schemas, rules"
```
Note: `backend/.env` is gitignored — its edit in Step 7 is a local operational change, not part of this commit.

---

### Task 2: `users` repository, uow, events, public facade

**Files:**
- Create: `backend/app/modules/users/repository.py`
- Create: `backend/app/modules/users/uow.py`
- Create: `backend/app/modules/users/events.py`
- Create: `backend/app/modules/users/dependencies.py`
- Create: `backend/app/modules/users/public.py`

**Interfaces:**
- Consumes: everything from Task 1.
- Produces: `AbstractUserRepository`, `UserRepository`, `AbstractUsersUnitOfWork` (with `mark_stale` and `invalidate_now`), `UsersUnitOfWork`, `UserCreated` event, `users.dependencies.get_uow`, `UsersApi` (facade: `get_user_by_id`, `is_protected_admin`, `find_by_email`, `find_by_external_id`, `create`, `update_profile`, `set_last_login`, `invalidate_user`), `get_users_api`. Re-exports `UserRead`, `UserStatus`, `UserCreated` for other modules to import through this facade rather than reaching into `users.schemas`/`users.constants`/`users.events` directly (rule #1).

No new test file for repository/uow themselves — matches `rbac/repository.py`'s own convention (exercised via `tests/users/test_services.py` and `tests/users/test_router.py` in Task 5, not unit-tested standalone).

- [ ] **Step 1: `backend/app/modules/users/repository.py`**
```python
"""Single access path to the users table."""

from abc import abstractmethod
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.integrations.cache.client import CacheClient
from app.modules.users.constants import UserStatus, UsersCacheKeys
from app.modules.users.models import User
from app.modules.users.schemas import UserRead


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
        """Block or unblock a user."""
        raise NotImplementedError


class UserRepository(AbstractUserRepository):
    """SQLAlchemy implementation. Every read of the users table goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: int) -> UserRead | None:
        """Return one user, or None when it does not exist. Cache-aside: a
        miss loads from the database and populates the cache."""
        return await self._cache.get_or_load(
            UsersCacheKeys.ENTITY, entity_id, UserRead, lambda: self._load_by_id(entity_id)
        )

    @helper
    async def _load_by_id(self, entity_id: int) -> UserRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
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
This is a straight move of the current `auth/repository.py` content with `Auth`→`Users` renaming and the import sources updated — no behavior change.

- [ ] **Step 2: `backend/app/modules/users/uow.py`**
```python
"""Transaction boundary for the users module."""

import logging
from abc import abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.users.repository import AbstractUserRepository, UserRepository

logger = logging.getLogger(__name__)


class AbstractUsersUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    users: AbstractUserRepository

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: int) -> None:
        """Queue a cache entity for invalidation once THIS uow's own commit() runs."""
        raise NotImplementedError

    @abstractmethod
    async def invalidate_now(self, entity: str, entity_id: int) -> None:
        """Bump a cache entity's version immediately, bypassing the mark_stale
        queue. For a cross-module orchestrator (e.g. auth's login flow) that
        writes through this module's facade but commits its OWN unit of
        work — this uow's commit() never runs in that case, so mark_stale
        would silently never flush. See UsersApi.invalidate_user and
        docs/superpowers/specs/2026-08-21-users-module-split-design.md.
        """
        raise NotImplementedError


class UsersUnitOfWork(AbstractUsersUnitOfWork):
    """Owns the transaction for the users module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, int]] = []
        self.users = UserRepository(session, cache)

    def mark_stale(self, entity: str, entity_id: int) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

    async def invalidate_now(self, entity: str, entity_id: int) -> None:
        """Bump a cache entity's version immediately, bypassing the queue."""
        await self._cache.bump_version(entity, entity_id)

    @database
    async def commit(self) -> None:
        """Commit the transaction, then invalidate every queued cache entity.

        Invalidation happens strictly after the database commit — bumping
        first would let a concurrent reader repopulate the cache from the
        pre-commit row. See references/caching.md#order-of-operations.
        """
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction and drop any queued invalidation."""
        await self._session.rollback()
        self._stale.clear()
        logger.warning("users unit of work rolled back")
```

- [ ] **Step 3: `backend/app/modules/users/events.py`**
```python
"""Events published by the users module."""

from app.core.events import DomainEvent
from app.modules.users.constants import UsersEvents


class UserCreated(DomainEvent):
    """Emitted after a new user has been synced from DX for the first time."""

    user_id: int
    email: str

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event."""
        return f"{UsersEvents.EXCHANGE}.user_created"
```

- [ ] **Step 4: `backend/app/modules/users/dependencies.py`**
```python
"""Dependency wiring for the users module.

The composition root: the only place that names a concrete class
(UsersUnitOfWork) instead of its Abstract* contract. Deliberately imports
nothing from rbac: get_update_user_status needs RbacApi (rbac.public), and
rbac.public needs users.public (for AssignRole's existence/protection
checks), which needs get_uow from this very file — so that factory lives
in users/router.py instead (Task 3), which is never imported by anything
else and can safely reach into rbac.public without closing that cycle.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.users.uow import AbstractUsersUnitOfWork, UsersUnitOfWork


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> UsersUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return UsersUnitOfWork(session, cache)
```

- [ ] **Step 5: `backend/app/modules/users/public.py`**
```python
"""Contract exposed to other modules. This is the ONLY file another module
may import from users — enforced by scripts/check_module_boundaries.py.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.users.constants import UserStatus, UsersCacheKeys
from app.modules.users.dependencies import get_uow
from app.modules.users.events import UserCreated
from app.modules.users.rules import UsersRules
from app.modules.users.schemas import UserRead
from app.modules.users.uow import AbstractUsersUnitOfWork

__all__ = [
    "UserCreated",
    "UserRead",
    "UserStatus",
    "UsersApi",
    "get_users_api",
]


class UsersApi:
    """Facade over the users table for other modules' cross-module needs:
    auth resolving/syncing the signed in user, rbac checking a role
    assignment's target user."""

    def __init__(self, uow: AbstractUsersUnitOfWork) -> None:
        self._uow = uow

    @facade
    async def get_user_by_id(self, user_id: int) -> UserRead | None:
        """Look up any user by id. For a single existence check from another
        module — never for bulk reads, which would mean that module wants its
        own list_page-shaped facade method instead."""
        return await self._uow.users.get_by_id(user_id)

    @facade
    async def is_protected_admin(self, user_id: int) -> bool:
        """True when user_id is the seeded break-glass admin account —
        used by rbac's AssignRole to reject reassigning its role."""
        user = await self.get_user_by_id(user_id)
        return user is not None and UsersRules.is_protected_admin_email(user.email)

    @facade
    async def find_by_email(self, email: str) -> UserRead | None:
        """Look up a user by email — for auth's DX-sync flow only."""
        return await self._uow.users.find_by_email(email)

    @facade
    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        """Look up a user by the DX subject identifier — for auth's DX-sync flow only."""
        return await self._uow.users.find_by_external_id(external_user_id)

    @facade
    async def create(
        self,
        *,
        email: str,
        name: str,
        external_user_id: str,
        employee_code: str | None,
        email_confirmed: bool,
    ) -> UserRead:
        """Create a new user synced from a DX profile — for auth's DX-sync
        flow only. Does not commit or invalidate: participates in the
        caller's own transaction. Safe without a matching invalidate_user
        call too, but the caller makes one anyway (see invalidate_user)."""
        return await self._uow.users.create(
            email=email,
            name=name,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
        )

    @facade
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
        """Sync an existing user's profile fields from DX — for auth's DX-sync
        flow only. Does not commit or invalidate: participates in the
        caller's own transaction. The caller MUST call invalidate_user(user_id)
        after its own commit succeeds — a returning user's profile is very
        likely already cached, unlike create's brand-new user_id."""
        return await self._uow.users.update_profile(
            user_id,
            email=email,
            name=name,
            external_user_id=external_user_id,
            employee_code=employee_code,
            email_confirmed=email_confirmed,
        )

    @facade
    async def set_last_login(self, user_id: int, at) -> None:
        """Record a completed login's timestamp — for auth's login flow only.
        Does not commit or invalidate: participates in the caller's own
        transaction. Covered by the same invalidate_user call as
        create/update_profile within one login."""
        await self._uow.users.set_last_login(user_id, at)

    @facade
    async def invalidate_user(self, user_id: int) -> None:
        """Bump this user's cache version immediately. For a cross-module
        orchestrator (auth's login flow) that wrote via create/update_profile/
        set_last_login above but commits its OWN unit of work, not this one
        — call this right after that commit succeeds. See uow.py's
        invalidate_now docstring."""
        await self._uow.invalidate_now(UsersCacheKeys.ENTITY, user_id)


async def get_users_api(uow: AbstractUsersUnitOfWork = Depends(get_uow)) -> UsersApi:
    """Provide the facade to other modules."""
    return UsersApi(uow)
```

- [ ] **Step 6: verify it imports cleanly and the boundary check stays clean**

Run: `cd backend && uv run python -c "from app.modules.users.public import UsersApi, get_users_api, UserRead, UserStatus, UserCreated; print('ok')"`
Expected: `ok`

Run: `python3 scripts/check_module_boundaries.py`
Expected: no violations (users doesn't yet import from auth/rbac, so this should already be clean).

- [ ] **Step 7: `ruff check` + `ruff format --check`**

Run: `uv run ruff check app/modules/users && uv run ruff format --check app/modules/users`
Expected: clean

- [ ] **Step 8: Commit**
```bash
git add backend/app/modules/users/repository.py backend/app/modules/users/uow.py backend/app/modules/users/events.py backend/app/modules/users/dependencies.py backend/app/modules/users/public.py
git commit -m "feat(users): repository, uow, events, and public facade"
```

---

### Task 3: `users` write use case + router, registered in `main.py`

**Files:**
- Create: `backend/app/modules/users/services/__init__.py` (empty)
- Create: `backend/app/modules/users/services/update_user_status.py`
- Create: `backend/app/modules/users/router.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `RbacApi`/`get_rbac_api` (`rbac.public`, unchanged), everything from Task 2.
- Produces: `UpdateUserStatus`, `GET /users`, `PATCH /users/{id}/status` mounted at `/api/v1/users`.

This is the task where `users` first imports from `rbac` — the factory needing `RbacApi` goes straight into `router.py`, not `dependencies.py`, per the spec's circular-import analysis (verified empirically in Step 4, not just reasoned about).

- [ ] **Step 1: `backend/app/modules/users/services/update_user_status.py`**
```python
"""Use case: block or unblock a user."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.rbac.public import RbacApi
from app.modules.users.constants import UserStatus, UsersCacheKeys
from app.modules.users.exceptions import CannotBlockLastAdmin, CannotModifyProtectedAdmin
from app.modules.users.rules import UsersRules
from app.modules.users.schemas import UserRead
from app.modules.users.uow import AbstractUsersUnitOfWork


class UpdateUserStatus(AbstractUseCase):
    """Block or unblock a user. Two independent rejections apply only when
    blocking: the seeded break-glass admin account is always protected
    (checked first, unconditional on admin count); the last admin is
    protected as long as no break-glass account exists to fall back on
    (rbac's own bus-factor rule, mirroring AssignRole for the analogous
    role-reassignment case)."""

    def __init__(self, uow: AbstractUsersUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, user_id: int, status: UserStatus) -> UserRead:
        if status == UserStatus.BLOCKED:
            target = await self._uow.users.get_by_id(user_id)
            if target is not None and UsersRules.is_protected_admin_email(target.email):
                raise CannotModifyProtectedAdmin()
            if await self._rbac_api.is_last_admin(user_id):
                raise CannotBlockLastAdmin()
        updated = await self._uow.users.set_status(user_id, status)
        self._uow.mark_stale(UsersCacheKeys.ENTITY, user_id)
        await self._uow.commit()
        return updated
```
This use case commits its OWN uow directly (not cross-module orchestrated), so the ordinary `mark_stale` + `commit()` pattern is correct as-is — no `invalidate_now` needed here.

- [ ] **Step 2: `backend/app/modules/users/router.py`**
```python
"""HTTP entry points of the users module. Router thinness (rule #10): every
function below only translates HTTP -> use-case call and wraps the result
in ApiResponse — no formatting/business logic lives here.
"""

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.core.pagination import Page, PaginationParams, pagination_params
from app.modules.rbac.public import RbacApi, get_rbac_api, require_permission
from app.modules.users.dependencies import get_uow
from app.modules.users.schemas import UserRead, UserStatusUpdate
from app.modules.users.services.update_user_status import UpdateUserStatus
from app.modules.users.uow import AbstractUsersUnitOfWork

router = APIRouter(prefix="/users", tags=["users"])


async def get_update_user_status(
    uow: AbstractUsersUnitOfWork = Depends(get_uow),
    rbac_api: RbacApi = Depends(get_rbac_api),
) -> UpdateUserStatus:
    """Provide the block/unblock use case."""
    return UpdateUserStatus(uow, rbac_api)


@router.get("")
async def list_users(
    pagination: PaginationParams = Depends(pagination_params),
    uow: AbstractUsersUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("user", "read")),
) -> ApiResponse[Page[UserRead]]:
    """List users for the admin user-management page."""
    items, total = await uow.users.list_page(pagination.limit, pagination.offset)
    page = Page[UserRead](items=items, total=total, limit=pagination.limit, offset=pagination.offset)
    return ApiResponse[Page[UserRead]](success=True, data=page)


@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: int,
    body: UserStatusUpdate,
    use_case: UpdateUserStatus = Depends(get_update_user_status),
    _user: UserRead = Depends(require_permission("user", "update_status")),
) -> ApiResponse[UserRead]:
    """Block or unblock a user. Blocking the last admin is rejected — see rbac's bus-factor rule."""
    updated = await use_case.execute(user_id, body.status)
    return ApiResponse[UserRead](success=True, data=updated)
```

- [ ] **Step 3: register the router**

In `backend/app/main.py`, add the import alongside the existing two:
```python
from app.modules.rbac.router import router as rbac_router
from app.modules.users.router import router as users_router
```
And add the include call alongside the existing two:
```python
app.include_router(auth_router, prefix="/api/v1")
app.include_router(rbac_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
```

- [ ] **Step 4: verify no circular import — empirically, not just by reasoning**

Run: `cd backend && python3 scripts/check_module_boundaries.py`
Expected: no violations.

Run: `uv run python -c "from app.main import app; print(len(app.openapi()['paths']), 'paths')"`
Expected: prints a path count with no `ImportError`/`RecursionError`. If this fails with a circular import, the factory needing the cross-module type is in the wrong file — re-check against the spec's dependency-shape section before moving anything.

- [ ] **Step 5: `ruff check` + `ruff format --check`**

Run: `uv run ruff check app/modules/users app/main.py && uv run ruff format --check app/modules/users app/main.py`
Expected: clean

- [ ] **Step 6: Commit**
```bash
git add backend/app/modules/users/services/ backend/app/modules/users/router.py backend/app/main.py
git commit -m "feat(users): block/unblock use case, GET/PATCH users router, mount at /api/v1/users"
```

---

### Task 4: Trim `auth` down to session/SSO only

**Files:**
- Modify: `backend/app/modules/auth/config.py`
- Modify: `backend/app/modules/auth/constants.py`
- Modify: `backend/app/modules/auth/exceptions.py`
- Modify: `backend/app/modules/auth/events.py`
- Modify: `backend/app/modules/auth/rules.py`
- Modify: `backend/app/modules/auth/schemas.py`
- Modify: `backend/app/modules/auth/uow.py`
- Modify: `backend/app/modules/auth/public.py`
- Modify: `backend/app/modules/auth/dependencies.py`
- Modify: `backend/app/modules/auth/services/sync_external_user.py`
- Modify: `backend/app/modules/auth/services/authenticate.py`
- Modify: `backend/app/modules/auth/router.py`
- Delete: `backend/app/modules/auth/models.py`
- Delete: `backend/app/modules/auth/repository.py`
- Delete: `backend/app/modules/auth/services/update_user_status.py` (moved to `users` in Task 3)

**Interfaces:**
- Consumes: `users.public.{UsersApi, get_users_api, UserRead, UserStatus, UserCreated}` (Task 2), `rbac.public.{RbacApi, get_rbac_api}` (unchanged).
- Produces: `AuthUnitOfWork` with no owned repository; `get_current_user` resolving through `UsersApi`; `AuthenticateWithDx` with a new `users_api` constructor param.

This task deliberately makes the whole module fail to import partway through — do every step in order, verify only at the end (Step 13), same as the original RBAC-vs-owner rename's "fail for the right reason" sequencing doesn't apply here since this is a coordinated multi-file rename, not a TDD cycle.

- [ ] **Step 1: `backend/app/modules/auth/config.py`** — remove the two fields Task 1 already duplicated into `UsersConfig`:
```python
"""Settings owned by the auth module.

Splitting settings per module keeps the global config from turning into a
dumping ground and lets a module be extracted with its configuration intact.
"""

from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import settings


class AuthConfig(BaseSettings):
    """Environment driven settings for the auth module's own session."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUTH__", extra="ignore")

    JWT_SECRET: str = "change-me-in-env"
    ACCESS_TOKEN_TTL_SECONDS: int = 1800
    REFRESH_TOKEN_TTL_SECONDS: int = 2592000
    COOKIE_SECURE: bool = True

    @property
    def cookie_domain(self) -> str | None:
        """Parent domain so session cookies are shared across subdomains
        (e.g. app.example.com <-> api.example.com), per
        docs/tasks/sso-login.md section 5.3. None in local dev, where the
        browser scopes the cookie to the request's own origin instead."""
        host = urlparse(settings.FRONTEND_BASE_URL).hostname or ""
        parts = host.split(".")
        if len(parts) <= 2 or host in ("localhost", "127.0.0.1"):
            return None
        return "." + ".".join(parts[-2:])


auth_settings = AuthConfig()
```

- [ ] **Step 2: `backend/app/modules/auth/constants.py`** — drop `UserStatus` (moved), `AuthLimits` (only `auth/models.py` used it, and that file is deleted this task — grep-verify first: `grep -rn "AuthLimits" app/ tests/` should show zero remaining references before deleting), the two admin-account error codes:
```python
"""Constants and enums owned by the auth module.

Other modules import these with an explicit alias:
    from app.auth import constants as auth_constants
"""

from enum import StrEnum
from typing import Literal

from app.modules.users.public import UserStatus


class AuthEvents:
    """Messaging identity owned by the auth module. See references/messaging.md."""

    EXCHANGE = "auth"


class AuthCookies:
    """Cookie names owned by the auth module's session."""

    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"

    SameSite = Literal["lax", "none", "strict"]


class AuthCacheNamespaces:
    """Redis key namespaces owned by the auth module.

    Passed to CacheKeyBuilder.session_key(namespace, identifier) — see
    app/integrations/cache/keys.py; no other file constructs these keys.
    """

    TOKEN_BLACKLIST = "auth:blacklist"


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    INVALID_CREDENTIALS = "auth_invalid_credentials"
    NOT_AUTHENTICATED = "auth_not_authenticated"
    USER_BLOCKED = "auth_user_blocked"


class LoginPolicy:
    """Statuses that must never be allowed to complete a login, regardless of role."""

    BLOCKED_STATUSES: frozenset[UserStatus] = frozenset({UserStatus.BLOCKED})
```
Note `UserStatus` is imported from `users.public`, not `users.constants` directly — rule #1, and this is the same re-export pattern `rbac/public.py` already uses for `UserRead` today.

- [ ] **Step 3: `backend/app/modules/auth/exceptions.py`**
```python
"""Errors owned by the auth module.

These live here rather than in a global module because each one encodes a
fact about auth: what counts as blocked, what counts as not-signed-in. The
mechanism they build on lives in app.exceptions.
"""

from app.core.exceptions import ForbiddenError, ValidationFailedError
from app.modules.auth.constants import ErrorCode


class UserBlocked(ForbiddenError):
    """Raised when a blocked user attempts to sign in or use a session."""

    code = ErrorCode.USER_BLOCKED
    message = "User account is blocked"


class InvalidCredentials(ValidationFailedError):
    """Raised when a login attempt fails validation (bad state, bad token, ...)."""

    code = ErrorCode.INVALID_CREDENTIALS
    message = "Invalid credentials"


class NotAuthenticated(ForbiddenError):
    """Raised when a request requires a session that isn't present or is invalid."""

    code = ErrorCode.NOT_AUTHENTICATED
    status_code = 401
    message = "Authentication required"
```

- [ ] **Step 4: `backend/app/modules/auth/events.py`**
```python
"""Events published by the auth module."""

from app.core.events import DomainEvent
from app.modules.auth.constants import AuthEvents


class UserLoggedIn(DomainEvent):
    """Emitted after a user completes the SSO login flow."""

    user_id: int

    @property
    def routing_key(self) -> str:
        """Return the key used when publishing this event."""
        return f"{AuthEvents.EXCHANGE}.user_logged_in"
```

- [ ] **Step 5: `backend/app/modules/auth/rules.py`**
```python
"""Business rules for the auth module.

Everything here is a pure decision: no I/O, no framework, no database. That is
what keeps these testable without fixtures, and it is the difference between
this class and the SSO sync/session services (out of scope for this issue),
which call these rules but also do I/O.
"""

from app.core.base.markers import rule
from app.modules.auth.constants import LoginPolicy
from app.modules.users.public import UserStatus


class AuthRules:
    """Every business decision about a user, grouped so call sites read as
    `AuthRules.can_login(...)` instead of a bare import."""

    @staticmethod
    @rule
    def can_login(status: UserStatus) -> bool:
        """Decide whether a user in this status is allowed to complete a login."""
        return status not in LoginPolicy.BLOCKED_STATUSES
```

- [ ] **Step 6: `backend/app/modules/auth/schemas.py`**
```python
"""Schemas for the auth module."""

from app.core.models import FrozenModel
from app.modules.users.public import UserRead


class MeResponse(FrozenModel):
    """/me's response: the user's profile plus their resolved role/permissions."""

    user: UserRead
    role_name: str
    permissions: list[str]
```

- [ ] **Step 7: `backend/app/modules/auth/uow.py`** — becomes a bare transaction coordinator, no owned repository:
```python
"""Transaction boundary for the auth module.

auth owns no tables after the users module split — this exists purely as
the shared request-scoped session's commit boundary for the login flow,
which writes across users (via UsersApi) and dx_core (DxTokenRepository)
within one atomic transaction. See
docs/superpowers/specs/2026-08-21-users-module-split-design.md.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork

logger = logging.getLogger(__name__)


class AbstractAuthUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""


class AuthUnitOfWork(AbstractAuthUnitOfWork):
    """Owns the shared session's commit boundary for the login flow. Owns no repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def commit(self) -> None:
        """Commit the transaction."""
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        logger.warning("auth unit of work rolled back")
```

- [ ] **Step 8: `backend/app/modules/auth/public.py`** — `AuthApi` no longer needs uow access at all:
```python
"""Contract exposed to other modules.

Other modules import this file and nothing else from auth. Reaching into
dependencies.py directly couples them to plumbing and makes this module
impossible to extract later.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.auth.dependencies import get_current_user
from app.modules.users.public import UserRead


class AuthApi:
    """Facade over the signed in user for other modules that need to know
    who is making the current request (e.g. rbac's require_permission)."""

    def __init__(self, user: UserRead) -> None:
        self._user = user

    @facade
    def current_user(self) -> UserRead:
        """Return the signed in user resolved for this request."""
        return self._user


async def get_auth_api(user: UserRead = Depends(get_current_user)) -> AuthApi:
    """Provide the facade to other modules."""
    return AuthApi(user)
```
`get_user_by_id` is gone from `AuthApi` entirely — it delegated to `self._uow.users.get_by_id`, and `auth`'s uow no longer has a `.users` repository to delegate to. Its one caller (`rbac/public.py`'s `get_assign_role`) is repointed to `UsersApi.get_user_by_id` in Task 5.

- [ ] **Step 9: `backend/app/modules/auth/dependencies.py`**
```python
"""Dependency wiring for the auth module.

The composition root: the only place that names a concrete class
(AuthUnitOfWork, DxTokenRepository, ...) instead of its Abstract* contract.

get_authenticate_with_dx needs RbacApi (rbac.public), and rbac.public
needs auth.public (for require_permission's current_user), which needs
get_current_user from this very file — so that factory lives in
auth/router.py instead, which is never imported by anything else and can
safely reach into rbac.public without closing that cycle. Depending on
users.public here (get_current_user, get_sync_external_user) is safe:
users.public never imports back to auth. See auth/router.py's and
rbac/public.py's docstrings, and
docs/superpowers/specs/2026-08-21-users-module-split-design.md.
"""

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import JwtCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.dependencies import get_dx_core_client
from app.integrations.dx_core.repository import AbstractDxTokenRepository, DxTokenRepository
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCacheNamespaces, AuthCookies
from app.modules.auth.exceptions import NotAuthenticated, UserBlocked
from app.modules.auth.rules import AuthRules
from app.modules.auth.services.issue_tokens import IssueTokens
from app.modules.auth.services.logout import LogoutUser
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork, AuthUnitOfWork
from app.modules.users.public import UserRead, UsersApi, get_users_api


async def get_uow(session: AsyncSession = Depends(get_session)) -> AuthUnitOfWork:
    """Provide the request scoped transaction coordinator for the login flow."""
    return AuthUnitOfWork(session)


async def get_dx_token_repository(
    session: AsyncSession = Depends(get_session),
) -> AbstractDxTokenRepository:
    """Provide the DX token repository, sharing this request's session/transaction
    with get_uow (both resolve from the same cached get_session dependency)."""
    return DxTokenRepository(session)


async def get_current_user(
    request: Request,
    users_api: UsersApi = Depends(get_users_api),
    cache: CacheClient = Depends(get_cache),
) -> UserRead:
    """Resolve the signed in user from the access_token session cookie.

    Rejects a token that decodes fine but was blacklisted by a prior
    /auth/logout call (app/modules/auth/services/logout.py) — expiry alone
    isn't enough once a user can end a session early. Raises the same
    NotAuthenticated whether the token's subject doesn't exist or has any
    other resolution failure — a deleted-but-still-signed-in user shouldn't
    read differently from "you're not signed in" to the client.
    """
    raw = request.cookies.get(AuthCookies.ACCESS_TOKEN)
    if raw is None:
        raise NotAuthenticated()
    try:
        claims = JwtCodec.decode(raw, secret=auth_settings.JWT_SECRET)
    except jwt.PyJWTError as exc:
        raise NotAuthenticated() from exc
    if claims.get("type") != "access":
        raise NotAuthenticated()

    blacklist_key = CacheKeyBuilder.session_key(AuthCacheNamespaces.TOKEN_BLACKLIST, claims["jti"])
    if await cache.get_json(blacklist_key) is not None:
        raise NotAuthenticated()

    user = await users_api.get_user_by_id(int(claims["sub"]))
    if user is None:
        raise NotAuthenticated()
    if not AuthRules.can_login(user.status):
        raise UserBlocked()
    return user


async def require_auth(user: UserRead = Depends(get_current_user)) -> UserRead:
    """Guard a route behind an authenticated session."""
    return user


async def get_sync_external_user(users_api: UsersApi = Depends(get_users_api)) -> SyncExternalUser:
    """Provide the DX profile sync use case."""
    return SyncExternalUser(users_api)


async def get_issue_tokens() -> IssueTokens:
    """Provide the app session token issuance use case."""
    return IssueTokens()


async def get_logout_user(
    dx_tokens: AbstractDxTokenRepository = Depends(get_dx_token_repository),
    dx_client: DxCoreClient = Depends(get_dx_core_client),
    cache: CacheClient = Depends(get_cache),
) -> LogoutUser:
    """Provide the logout use case."""
    return LogoutUser(dx_tokens, dx_client, cache)
```
Behavior note flagged deliberately in the docstring: previously a resolved-but-missing user raised `UserNotFound`; now it raises `NotAuthenticated` (that exception no longer exists in `auth` — `UserNotFound` moved to `users`, and reaching into `users.exceptions` for a session-resolution edge case would be the wrong direction anyway).

- [ ] **Step 10: `backend/app/modules/auth/services/sync_external_user.py`**
```python
"""Use case: upsert the local User from a DX profile."""

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.dx_core.client import DxUserProfile
from app.modules.users.public import UserRead, UsersApi


class SyncExternalUser(AbstractUseCase):
    """Sync a DX /oauth2/userinfo profile into the users table via UsersApi
    — auth no longer owns this table.

    Role assignment is no longer this use case's job — see
    AuthenticateWithDx, which grants the default rbac role only for a brand
    new user, right after this returns is_new=True. Does not commit or
    invalidate the cache itself: AuthenticateWithDx owns both, since it
    orchestrates this alongside DX-token-save and role-assignment writes
    that must all succeed or fail together in one transaction.
    """

    def __init__(self, users_api: UsersApi) -> None:
        self._users_api = users_api

    @use_case
    async def execute(self, profile: DxUserProfile) -> tuple[UserRead, bool]:
        """Return (user, is_new)."""
        existing = await self._users_api.find_by_external_id(profile.sub)
        if existing is None:
            existing = await self._users_api.find_by_email(profile.email)

        if existing is None:
            user = await self._users_api.create(
                email=profile.email,
                name=profile.name,
                external_user_id=profile.sub,
                employee_code=profile.employee_code,
                email_confirmed=profile.email_verified,
            )
            return user, True

        user = await self._users_api.update_profile(
            existing.id,
            email=profile.email,
            name=profile.name,
            external_user_id=profile.sub,
            employee_code=profile.employee_code,
            email_confirmed=profile.email_verified,
        )
        return user, False
```

- [ ] **Step 11: `backend/app/modules/auth/services/authenticate.py`**
```python
"""Use case: complete the DX OAuth2 callback (docs/tasks/sso-login.md #4 Step 4)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.events import EventBus
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.events import UserLoggedIn
from app.modules.auth.exceptions import UserBlocked
from app.modules.auth.rules import AuthRules
from app.modules.auth.services.issue_tokens import AppTokenSet, IssueTokens
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.rbac.public import RbacApi
from app.modules.users.public import UserCreated, UserRead, UsersApi


@dataclass(frozen=True)
class DxLoginResult:
    """What the callback route needs to finish the HTTP response."""

    user: UserRead
    tokens: AppTokenSet


class AuthenticateWithDx(AbstractUseCase):
    """Exchange code -> profile -> sync user -> policy check -> store DX tokens -> issue session.

    One class, one operation, per core/base/use_case.py rule #9 — the
    callback endpoint's entire business logic lives here so router.py stays
    a thin HTTP adapter that only translates the result into a redirect.
    The caller (router) is responsible for validating/consuming the PKCE
    state before calling this — that is transport-level (cache lookup), not
    a business decision this use case needs to own.

    For a brand new user, also grants the seeded default rbac role via
    rbac's public facade (never rbac's internal dependencies.py/services/ —
    see fastapi-modular-scaffold rule #1) in the same transaction this use
    case commits. users_api.invalidate_user runs right after that commit
    succeeds: the write to the users table happened through UsersApi, but
    the commit that makes it durable is this use case's own uow, not
    users' — so users' usual mark_stale-then-commit dance doesn't apply
    here. See docs/superpowers/specs/2026-08-21-users-module-split-design.md.
    """

    def __init__(
        self,
        uow: AbstractAuthUnitOfWork,
        dx_tokens: AbstractDxTokenRepository,
        dx_client: DxCoreClient,
        sync_user: SyncExternalUser,
        issue_tokens: IssueTokens,
        events: EventBus,
        rbac_api: RbacApi,
        users_api: UsersApi,
    ) -> None:
        self._uow = uow
        self._dx_tokens = dx_tokens
        self._dx_client = dx_client
        self._sync_user = sync_user
        self._issue_tokens = issue_tokens
        self._events = events
        self._rbac_api = rbac_api
        self._users_api = users_api

    @use_case
    async def execute(self, code: str, code_verifier: str) -> DxLoginResult:
        token = await self._dx_client.exchange_code(code, code_verifier)
        profile = await self._dx_client.fetch_userinfo(token.access_token)

        user, is_new = await self._sync_user.execute(profile)
        if not AuthRules.can_login(user.status):
            raise UserBlocked()

        if is_new:
            await self._rbac_api.assign_default_role(user.id)

        expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)
        await self._dx_tokens.save(user.id, token, expires_at=expires_at)
        await self._users_api.set_last_login(user.id, datetime.now(UTC))
        await self._uow.commit()
        await self._users_api.invalidate_user(user.id)

        tokens = await self._issue_tokens.execute(user)

        if is_new:
            await self._events.publish(UserCreated(user_id=user.id, email=user.email))
        await self._events.publish(UserLoggedIn(user_id=user.id))

        return DxLoginResult(user=user, tokens=tokens)
```

- [ ] **Step 12: `backend/app/modules/auth/router.py`** — drop the two user-admin endpoints (moved to `users/router.py`), gain `users_api` in the `AuthenticateWithDx` factory:
```python
"""HTTP entry points of the auth module.

/oauth/dx/start and /oauth/dx/callback are top-level browser navigations
(the SPA never calls them via fetch/XHR), so they redirect rather than
return the ApiResponse envelope — the browser's own address bar is where a
JSON body would otherwise be dumped raw. /logout and /me are ordinary API
endpoints and use the envelope like every other module's routes. See
docs/tasks/sso-login.md sections 5.1 and 11 for the exact contract.
"""

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core.events import EventBus, get_event_bus
from app.core.models import ApiResponse
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.dx_core.client import DxCoreClient
from app.integrations.dx_core.constants import DxCacheNamespaces, DxDefaults
from app.integrations.dx_core.dependencies import get_dx_core_client
from app.integrations.dx_core.exceptions import DxCoreUnavailable, TokenExchangeFailed
from app.integrations.dx_core.repository import AbstractDxTokenRepository
from app.modules.auth.constants import AuthCookies
from app.modules.auth.dependencies import (
    get_dx_token_repository,
    get_issue_tokens,
    get_logout_user,
    get_sync_external_user,
    get_uow,
    require_auth,
)
from app.modules.auth.exceptions import UserBlocked
from app.modules.auth.schemas import MeResponse
from app.modules.auth.services.authenticate import AuthenticateWithDx
from app.modules.auth.services.issue_tokens import IssueTokens
from app.modules.auth.services.logout import LogoutUser
from app.modules.auth.services.sync_external_user import SyncExternalUser
from app.modules.auth.uow import AbstractAuthUnitOfWork
from app.modules.auth.utils import AuthSessionResponses
from app.modules.rbac.public import RbacApi, get_rbac_api
from app.modules.users.public import UserRead, UsersApi, get_users_api

router = APIRouter(prefix="/auth", tags=["auth"])


async def get_authenticate_with_dx(
    uow: AbstractAuthUnitOfWork = Depends(get_uow),
    dx_tokens: AbstractDxTokenRepository = Depends(get_dx_token_repository),
    dx_client: DxCoreClient = Depends(get_dx_core_client),
    sync_user: SyncExternalUser = Depends(get_sync_external_user),
    issue_tokens: IssueTokens = Depends(get_issue_tokens),
    events: EventBus = Depends(get_event_bus),
    rbac_api: RbacApi = Depends(get_rbac_api),
    users_api: UsersApi = Depends(get_users_api),
) -> AuthenticateWithDx:
    """Provide the DX OAuth2 callback use case."""
    return AuthenticateWithDx(uow, dx_tokens, dx_client, sync_user, issue_tokens, events, rbac_api, users_api)


@router.get("/oauth/dx/start")
async def start_dx_oauth(
    cache: CacheClient = Depends(get_cache),
    dx_client: DxCoreClient = Depends(get_dx_core_client),
) -> RedirectResponse:
    """Begin the WeUp DX OAuth2 + PKCE flow."""
    pair = dx_client.generate_pkce_pair()
    key = CacheKeyBuilder.session_key(DxCacheNamespaces.PKCE_STATE, pair.state)
    await cache.set_json(key, {"code_verifier": pair.code_verifier}, ttl=DxDefaults.PKCE_STATE_TTL_SECONDS)
    url = dx_client.build_authorize_url(pair.state, pair.code_challenge)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get("/oauth/dx/callback")
async def dx_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    cache: CacheClient = Depends(get_cache),
    authenticate: AuthenticateWithDx = Depends(get_authenticate_with_dx),
) -> RedirectResponse:
    """Handle the DX OAuth2 callback: exchange code, sync user, issue session.

    Every failure mode redirects to the SPA's login page with a stable
    ?error= code instead of raising — a mid-flow JSON error would show raw
    text in the user's browser instead of a page it controls.
    """
    if error or not code or not state:
        return AuthSessionResponses.login_error_redirect("sso_denied")

    key = CacheKeyBuilder.session_key(DxCacheNamespaces.PKCE_STATE, state)
    stored = await cache.get_json(key)
    if stored is None:
        return AuthSessionResponses.login_error_redirect("sso_state")
    await cache.delete(key)  # single-use, whether or not the exchange below succeeds

    try:
        result = await authenticate.execute(code, stored["code_verifier"])
    except (TokenExchangeFailed, DxCoreUnavailable):
        return AuthSessionResponses.login_error_redirect("sso_failed")
    except UserBlocked:
        return AuthSessionResponses.login_error_redirect("suspended")

    response = RedirectResponse(settings.FRONTEND_BASE_URL, status_code=status.HTTP_302_FOUND)
    AuthSessionResponses.set_session_cookies(response, result.tokens)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: UserRead = Depends(require_auth),
    logout_user: LogoutUser = Depends(get_logout_user),
) -> ApiResponse[None]:
    """Revoke the DX token and clear the app session."""
    await logout_user.execute(
        user.id,
        request.cookies.get(AuthCookies.ACCESS_TOKEN),
        request.cookies.get(AuthCookies.REFRESH_TOKEN),
    )
    AuthSessionResponses.clear_session_cookies(response)
    return ApiResponse[None](success=True)


@router.get("/me")
async def me(
    user: UserRead = Depends(require_auth), rbac: RbacApi = Depends(get_rbac_api)
) -> ApiResponse[MeResponse]:
    """Return the signed in user's profile plus their role and permissions —
    what the frontend's PermissionProvider seeds from."""
    summary = await rbac.role_summary_for_user(user.id)
    body = MeResponse(user=user, role_name=summary.role_name, permissions=summary.permissions)
    return ApiResponse[MeResponse](success=True, data=body)
```

- [ ] **Step 13: delete the two now-empty-of-purpose files**

Run: `rm backend/app/modules/auth/models.py backend/app/modules/auth/repository.py backend/app/modules/auth/services/update_user_status.py`

- [ ] **Step 14: verify — this is the first point the whole module tree should import cleanly again**

Run: `cd backend && uv run python -c "from app.modules.auth.router import router; print('ok')"`
Expected: `ok` (will fail until Task 5 also updates `rbac`, since `auth` doesn't import `rbac`'s broken bits directly but `app.main` does — if this succeeds standalone, good; the real end-to-end check is Task 5's Step 3).

Run: `grep -rn "AuthLimits" app/ tests/` (from Step 2's note)
Expected: no results — confirms it was safe to drop.

- [ ] **Step 15: `ruff check` + `ruff format --check`**

Run: `uv run ruff check app/modules/auth && uv run ruff format --check app/modules/auth`
Expected: clean (import errors from the still-broken `rbac`/tests cross-references don't block ruff, which is a syntax/style linter, not a type checker).

- [ ] **Step 16: Commit**
```bash
git add -A backend/app/modules/auth/
git commit -m "refactor(auth): trim to session/SSO only — user administration moved to users"
```

---

### Task 5: Repoint `rbac` at `users`

**Files:**
- Modify: `backend/app/modules/rbac/public.py`
- Modify: `backend/app/modules/rbac/router.py`

**Interfaces:**
- Consumes: `users.public.{UsersApi, get_users_api, UserRead}` (Task 2).
- Produces: `get_assign_role` wired to `UsersApi` instead of the now-gone `AuthApi.get_user_by_id`/`is_protected_admin`.

- [ ] **Step 1: `backend/app/modules/rbac/public.py`**
```python
"""Contract exposed to other modules. This is the ONLY file another module
may import from rbac — enforced by scripts/check_module_boundaries.py.
"""

from fastapi import Depends

from app.core.base.markers import facade
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.rbac.constants import RbacDefaults
from app.modules.rbac.dependencies import get_uow
from app.modules.rbac.exceptions import PermissionDenied
from app.modules.rbac.rules import RbacRules
from app.modules.rbac.schemas import RoleSummary
from app.modules.rbac.services.assign_default_role import AssignDefaultRole
from app.modules.rbac.services.assign_role import AssignRole
from app.modules.rbac.uow import AbstractRbacUnitOfWork
from app.modules.users.public import UserRead, UsersApi, get_users_api


class RbacApi:
    """Facade over role/permission lookups other modules need."""

    def __init__(self, uow: AbstractRbacUnitOfWork) -> None:
        self._uow = uow

    @facade
    async def assign_default_role(self, user_id: int) -> None:
        """Grant the seeded default role. See services/assign_default_role.py."""
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
    async def is_last_admin(self, user_id: int) -> bool:
        """True if user_id holds the admin role and is the only one who does —
        used by users' UpdateUserStatus to block blocking the last admin."""
        role = await self._uow.user_roles.get_role_for_user(user_id)
        if role is None or role.name != RbacDefaults.ADMIN_ROLE_NAME:
            return False
        admin_grants = await self._uow.roles.count_users_with_role(role.id)
        return RbacRules.blocks_last_admin_removal(role.name, admin_grants)


async def get_rbac_api(uow: AbstractRbacUnitOfWork = Depends(get_uow)) -> RbacApi:
    """Provide the facade to other modules."""
    return RbacApi(uow)


async def get_assign_role(
    uow: AbstractRbacUnitOfWork = Depends(get_uow),
    users_api: UsersApi = Depends(get_users_api),
) -> AssignRole:
    """Provide the assign-role use case, wired to users' existence and
    protected-admin checks."""
    return AssignRole(uow, users_api.get_user_by_id, users_api.is_protected_admin)


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
Only two things changed from the current file: the docstring on `is_last_admin` ("auth's" → "users' UpdateUserStatus"), and `get_assign_role` now depends on `UsersApi` instead of `AuthApi` for the two checks `AssignRole` needs.

- [ ] **Step 2: `backend/app/modules/rbac/router.py`** — one import line changes:

Replace:
```python
from app.modules.auth.public import UserRead
```
with:
```python
from app.modules.users.public import UserRead
```
Nothing else in this file changes.

- [ ] **Step 3: verify the whole app imports and the boundary check is clean — the real end-to-end check for the Task 4/5 split**

Run: `cd backend && python3 scripts/check_module_boundaries.py`
Expected: `✓ No cross-module boundary violations found.`

Run: `uv run python -c "from app.main import app; print(len(app.openapi()['paths']), 'paths')"`
Expected: prints a path count, no `ImportError`. If this fails, the error traceback names the exact circular chain — cross-check it against the spec's "Cross-module dependency shape" section and this task's docstrings before changing anything blind.

- [ ] **Step 4: `ruff check` + `ruff format --check`**

Run: `uv run ruff check app/modules/rbac && uv run ruff format --check app/modules/rbac`
Expected: clean

- [ ] **Step 5: Commit**
```bash
git add backend/app/modules/rbac/public.py backend/app/modules/rbac/router.py
git commit -m "refactor(rbac): depend on users instead of auth for existence/protection checks"
```

---

### Task 6: Move and update tests

**Files:**
- Create: `backend/tests/users/test_services.py`
- Create: `backend/tests/users/test_router.py`
- Modify: `backend/tests/auth/test_services.py`
- Modify: `backend/tests/auth/test_router.py`
- Modify: `backend/tests/auth/test_rules.py`
- Modify: `backend/tests/rbac/test_router.py`

This task doesn't introduce new behavior — it's the test suite catching up to Tasks 1-5. Run the full suite first to get a precise list of every failure before editing, rather than guessing.

- [ ] **Step 1: see the full damage**

Run: `cd backend && uv run pytest -q 2>&1 | tail -60`
Expected: a mix of collection errors (`ModuleNotFoundError: app.modules.auth.models`, `ImportError: cannot import name 'UserRead' from 'app.modules.auth.schemas'`, etc.) and real failures (`FakeAuthUnitOfWork` missing `.users`, `AssignRole`/`UpdateUserStatus` fakes needing a `UsersApi`-shaped double instead of the old `AuthApi`-shaped one). Use this output as the checklist for the remaining steps — it will name every file needing an edit.

- [ ] **Step 2: `backend/tests/users/test_services.py`** — the moved `TestUpdateUserStatus` from `tests/auth/test_services.py`, plus a users-shaped `FakeUsersUnitOfWork`:
```python
"""Unit tests for the users module's use cases. No database — every
collaborator is a fake implementing the module's own Abstract* contract.
Router-level behavior is covered separately in tests/users/test_router.py.
"""

from datetime import UTC, datetime

import pytest

from app.modules.users.config import users_settings
from app.modules.users.constants import UserStatus
from app.modules.users.exceptions import CannotBlockLastAdmin, CannotModifyProtectedAdmin
from app.modules.users.repository import AbstractUserRepository
from app.modules.users.schemas import UserRead
from app.modules.users.services.update_user_status import UpdateUserStatus
from app.modules.users.uow import AbstractUsersUnitOfWork


class FakeUserRepository(AbstractUserRepository):
    def __init__(self) -> None:
        self._rows: dict[int, UserRead] = {}
        self._next_id = 1

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
        self, *, email: str, name: str, external_user_id: str, employee_code: str | None, email_confirmed: bool
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
        existing = self._rows.get(user_id)
        if existing is not None:
            self._rows[user_id] = existing.model_copy(update={"last_login_at": at})

    async def set_status(self, user_id: int, status: UserStatus) -> UserRead:
        existing = self._rows[user_id]
        updated = existing.model_copy(update={"status": status})
        self._rows[user_id] = updated
        return updated


class FakeUsersUnitOfWork(AbstractUsersUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, int]] = []

    def mark_stale(self, entity: str, entity_id: int) -> None:
        self.stale.append((entity, entity_id))

    async def invalidate_now(self, entity: str, entity_id: int) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeRbacApi:
    """Duck-typed stand-in for app.modules.rbac.public.RbacApi — UpdateUserStatus
    only calls is_last_admin, so that's the only method this fake needs."""

    def __init__(self, *, last_admin_ids: frozenset[int] = frozenset()) -> None:
        self._last_admin_ids = last_admin_ids

    async def is_last_admin(self, user_id: int) -> bool:
        return user_id in self._last_admin_ids


class TestUpdateUserStatus:
    """UpdateUserStatus: block/unblock a user, rejecting a block that would
    leave zero users holding the admin role."""

    async def test_blocks_an_active_user(self) -> None:
        uow = FakeUsersUnitOfWork()
        user = await uow.users.create(
            email="target@example.com",
            name="Target",
            external_user_id="dx-target",
            employee_code=None,
            email_confirmed=True,
        )
        rbac_api = FakeRbacApi()

        updated = await UpdateUserStatus(uow, rbac_api).execute(user.id, UserStatus.BLOCKED)

        assert updated.status is UserStatus.BLOCKED
        assert uow.commits == 1

    async def test_unblocking_never_consults_the_bus_factor_rule(self) -> None:
        uow = FakeUsersUnitOfWork()
        user = await uow.users.create(
            email="target@example.com",
            name="Target",
            external_user_id="dx-target",
            employee_code=None,
            email_confirmed=True,
        )
        rbac_api = FakeRbacApi(last_admin_ids=frozenset({user.id}))  # would block if this were a BLOCK

        updated = await UpdateUserStatus(uow, rbac_api).execute(user.id, UserStatus.ACTIVE)

        assert updated.status is UserStatus.ACTIVE

    async def test_rejects_blocking_the_last_admin(self) -> None:
        uow = FakeUsersUnitOfWork()
        user = await uow.users.create(
            email="admin@example.com",
            name="Admin",
            external_user_id="dx-admin",
            employee_code=None,
            email_confirmed=True,
        )
        rbac_api = FakeRbacApi(last_admin_ids=frozenset({user.id}))

        with pytest.raises(CannotBlockLastAdmin):
            await UpdateUserStatus(uow, rbac_api).execute(user.id, UserStatus.BLOCKED)

        assert uow.commits == 0

    async def test_rejects_blocking_the_protected_admin(self, monkeypatch) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", "protected@example.com")
        uow = FakeUsersUnitOfWork()
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

- [ ] **Step 3: `backend/tests/users/test_router.py`** — the moved `TestListUsers`/`TestUpdateUserStatus` router tests from `tests/auth/test_router.py`:
```python
"""Integration tests for app.modules.users.router. Real Postgres via the
`client` fixture."""

from httpx import AsyncClient
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.config import users_settings
from app.modules.users.models import User


async def _login_with_permissions(
    client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]
) -> int:
    """Log in a real user (via a direct session cookie, same trick auth's
    own router tests use) and grant a role carrying exactly `permissions`."""
    from app.core.security import JwtCodec
    from app.modules.auth.config import auth_settings
    from app.modules.auth.constants import AuthCookies

    async with engine.begin() as conn:
        user_result = await conn.execute(
            insert(User).values(
                email="actor@example.com",
                name="Actor",
                status="active",
                external_user_id="dx-actor",
                employee_code=None,
                email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]

        role_result = await conn.execute(insert(Role).values(name="test-role", is_system=False))
        role_id = role_result.inserted_primary_key[0]

        for resource, action in permissions:
            perm_result = await conn.execute(
                insert(Permission).values(resource=resource, action=action, description_key="x")
            )
            permission_id = perm_result.inserted_primary_key[0]
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))

        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": "test-jti"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


class TestListUsers:
    async def test_requires_user_read_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.get("/api/v1/users")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_lists_users_with_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[("user", "read")])

        response = await client.get("/api/v1/users")

        assert response.status_code == 200
        assert response.json()["data"]["total"] >= 1


class TestUpdateUserStatus:
    async def test_blocks_a_user(self, client: AsyncClient, engine: AsyncEngine) -> None:
        admin_id = await _login_with_permissions(client, engine, permissions=[("user", "update_status")])
        async with engine.begin() as conn:
            target = await conn.execute(
                insert(User).values(
                    email="target@example.com",
                    name="Target",
                    status="active",
                    external_user_id="dx-target",
                    employee_code=None,
                    email_confirmed=True,
                )
            )
            target_id = target.inserted_primary_key[0]

        response = await client.patch(f"/api/v1/users/{target_id}/status", json={"status": "blocked"})

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["status"] == "blocked"
        assert target_id != admin_id  # sanity: didn't accidentally block the actor itself

    async def test_rejects_blocking_the_last_admin(self, client: AsyncClient, engine: AsyncEngine) -> None:
        actor_id = await _login_with_permissions(client, engine, permissions=[("user", "update_status")])
        async with engine.begin() as conn:
            admin_role_id = (await conn.execute(select(Role.id).where(Role.name == "admin"))).scalar_one()
            update_status_permission_id = (
                await conn.execute(
                    select(Permission.id).where(
                        Permission.resource == "user", Permission.action == "update_status"
                    )
                )
            ).scalar_one()
            await conn.execute(
                insert(RolePermission).values(
                    role_id=admin_role_id, permission_id=update_status_permission_id
                )
            )
            await conn.execute(
                update(UserRole).where(UserRole.user_id == actor_id).values(role_id=admin_role_id)
            )

        response = await client.patch(f"/api/v1/users/{actor_id}/status", json={"status": "blocked"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "users_cannot_block_last_admin"

    async def test_rejects_blocking_the_protected_admin(
        self, client: AsyncClient, engine: AsyncEngine, monkeypatch
    ) -> None:
        monkeypatch.setattr(users_settings, "ADMIN_EMAIL", "protected-router@example.com")
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

        response = await client.patch(f"/api/v1/users/{target_id}/status", json={"status": "blocked"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "users_cannot_modify_protected_admin"
```
Note the error code assertions changed from `auth_cannot_block_last_admin`/`auth_cannot_modify_protected_admin` to `users_...` — matches Task 1's constants.

- [ ] **Step 4: `backend/tests/auth/test_services.py`** — remove what moved, adapt what stayed

Remove entirely: `TestUpdateUserStatus` class, `FakeUserRepository` class (moved to `tests/users/test_services.py`), the `CannotBlockLastAdmin, CannotModifyProtectedAdmin` names from the `app.modules.auth.exceptions` import (both gone from that module now).

Adapt `FakeAuthUnitOfWork`: it no longer wraps a `FakeUserRepository` (auth owns no repository). Replace:
```python
class FakeAuthUnitOfWork(AbstractAuthUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, int]] = []

    def mark_stale(self, entity: str, entity_id: int) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
```
with:
```python
class FakeAuthUnitOfWork(AbstractAuthUnitOfWork):
    """In-memory transaction coordinator. commit/rollback are no-ops that
    just count calls — auth owns no repository, so there's nothing to fake here."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
```

Add a `FakeUsersApi` duck-typed stand-in (used by `TestSyncExternalUser` and `TestAuthenticateWithDx`), and rewrite those two test classes to construct `SyncExternalUser(users_api)` / `AuthenticateWithDx(..., users_api=...)` instead of the old `SyncExternalUser(uow)` / `AuthenticateWithDx(uow, ..., rbac_api)`. The exact shape:
```python
class FakeUsersApi:
    """Duck-typed stand-in for app.modules.users.public.UsersApi."""

    def __init__(self) -> None:
        self._rows: dict[int, UserRead] = {}
        self._by_email: dict[str, int] = {}
        self._by_external_id: dict[str, int] = {}
        self._next_id = 1
        self.invalidated: list[int] = []

    async def get_user_by_id(self, user_id: int) -> UserRead | None:
        return self._rows.get(user_id)

    async def find_by_email(self, email: str) -> UserRead | None:
        user_id = self._by_email.get(email)
        return self._rows.get(user_id) if user_id else None

    async def find_by_external_id(self, external_user_id: str) -> UserRead | None:
        user_id = self._by_external_id.get(external_user_id)
        return self._rows.get(user_id) if user_id else None

    async def create(
        self, *, email: str, name: str, external_user_id: str, employee_code: str | None, email_confirmed: bool
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
        self._by_email[email] = user.id
        self._by_external_id[external_user_id] = user.id
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
        self._by_email[email] = user_id
        self._by_external_id[external_user_id] = user_id
        return updated

    async def set_last_login(self, user_id: int, at: datetime) -> None:
        existing = self._rows.get(user_id)
        if existing is not None:
            self._rows[user_id] = existing.model_copy(update={"last_login_at": at})

    async def invalidate_user(self, user_id: int) -> None:
        self.invalidated.append(user_id)
```
Add `from app.modules.users.public import UserRead` (replacing the old `from app.modules.auth.schemas import UserRead`) and `from app.modules.users.constants import UserStatus` to this file's imports. Update `TestSyncExternalUser`'s and `TestAuthenticateWithDx`'s test bodies to construct `FakeUsersApi()` instead of the old `FakeAuthUnitOfWork()`+`FakeUserRepository`, and pass it as `SyncExternalUser(users_api)` / into `AuthenticateWithDx(..., rbac_api=..., users_api=...)`. Follow the full-suite failure output from Step 1 for the exact call sites — there are roughly 6-7 test methods across these two classes to touch, each a small constructor-argument change, not a logic change.

- [ ] **Step 5: `backend/tests/auth/test_router.py`** — remove what moved, fix imports

Remove entirely: `TestListUsers` class, `TestUpdateUserStatus` class (both moved to `tests/users/test_router.py`), the `_login_with_permissions` helper (moved with them — `TestOAuthCallback`/`TestLogout` don't need it).

Change:
```python
from app.modules.auth.models import User
```
to:
```python
from app.modules.users.models import User
```
(auth's router tests that construct a `User` row directly for OAuth-callback fixtures still need the model — it just lives in a different module now.)

Change:
```python
from app.modules.auth.config import auth_settings
```
This import stays (still used for `JWT_SECRET` in whatever session-cookie-minting helper remains in this file, if any — verify against Step 1's output; the `ADMIN_EMAIL` monkeypatch calls that used `auth_settings` moved to `tests/users/test_router.py` using `users_settings` instead).

- [ ] **Step 6: `backend/tests/auth/test_rules.py`** — remove the moved test class

Remove `TestIsProtectedAdminEmail` (moved to `tests/users/test_rules.py` in Task 1) and its `from app.modules.auth.config import auth_settings` import if nothing else in the file uses it.

- [ ] **Step 7: `backend/tests/rbac/test_router.py`** — three import lines change

Replace:
```python
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.auth.models import User
```
with:
```python
from app.modules.auth.constants import AuthCookies
from app.modules.users.config import users_settings
from app.modules.users.models import User
```
And update every `auth_settings` reference in this file (the `monkeypatch.setattr(auth_settings, "ADMIN_EMAIL", ...)` calls in `TestAssignUserRole`) to `users_settings`.

- [ ] **Step 8: run the full suite, iterate against real failures**

Run: `uv run pytest -q 2>&1 | tail -80`

Fix whatever's left — this plan's code samples cover the structural moves precisely, but a full mechanical pass like this commonly turns up one or two small missed references (an unused import ruff flags, a fixture name typo). Iterate Steps 2-7 against the actual error output rather than assuming this document caught every last one.

Expected once clean: same 4 pre-existing unrelated failures this session has consistently seen (`TestOAuthCallback::test_new_user_login_sets_session_cookies_and_redirects_to_frontend`, `test_me_returns_the_signed_in_users_profile`, `test_state_is_single_use`, `TestLogout::test_logout_clears_cookies_and_blacklists_the_session` — all a pre-existing `KeyError: 'client_id'` on a query-string parse, unrelated to this change), plus every new/moved test passing. Total count will be higher than the pre-split baseline (new `tests/users/` tests add more than the removed duplicates subtract).

- [ ] **Step 9: `ruff check` + `ruff format --check` + module boundary**

Run: `uv run ruff check app tests && uv run ruff format --check app tests && python3 scripts/check_module_boundaries.py`
Expected: all clean.

- [ ] **Step 10: Commit**
```bash
git add backend/tests/
git commit -m "test: move users tests to tests/users/, update auth/rbac tests for the split"
```

---

### Task 7: Seed script, final verification, frontend note

**Files:**
- Modify: `backend/app/seeds/seed_admin.py`

**Interfaces:**
- Consumes: `users.config.users_settings`, `users.constants.UserStatus`, `users.models.User`, `rbac.constants.RbacDefaults` (unchanged), `rbac.models.Role`/`UserRole` (unchanged).

- [ ] **Step 1: update the three import lines**

In `backend/app/seeds/seed_admin.py`, replace:
```python
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import UserStatus
from app.modules.auth.models import User
```
with:
```python
from app.modules.users.config import users_settings
from app.modules.users.constants import UserStatus
from app.modules.users.models import User
```
And every `auth_settings.ADMIN_EMAIL`/`auth_settings.ADMIN_NAME` reference in this file (the docstring's env var name, the `if not auth_settings.ADMIN_EMAIL:` guard, the `User(email=auth_settings.ADMIN_EMAIL, name=auth_settings.ADMIN_NAME, ...)` construction, and the log lines) to `users_settings.ADMIN_EMAIL`/`users_settings.ADMIN_NAME`. Also update the module docstring's `AUTH__ADMIN_EMAIL` mention to `USERS__ADMIN_EMAIL`.

- [ ] **Step 2: real DB re-verification — confirm the renamed env var actually works against the account already seeded there**

Run: `cd backend && uv run ruff check app/seeds/seed_admin.py && uv run ruff format --check app/seeds/seed_admin.py`
Expected: clean

Run: `uv run python -m app.seeds.seed_admin`
Expected: exits 0, no error (picks up `USERS__ADMIN_EMAIL` from `.env`, which Task 1 already renamed).

Run: `psql "postgresql://postgres:postgres@localhost:5435/itsm" -c "select u.email, r.name from users u join user_roles ur on ur.user_id=u.id join roles r on r.id=ur.role_id where u.email='hoangvandieu.weup@gmail.com';"`
Expected: one row, unchanged from before this whole plan — role still `admin`. Confirms the split didn't touch actual data, only which Python module owns the code that reads/writes it.

- [ ] **Step 3: full-repo final verification**

Run: `uv run ruff check app tests && uv run ruff format --check app tests && python3 scripts/check_module_boundaries.py && uv run pytest -q 2>&1 | tail -10`
Expected: all clean; test counts match Task 6 Step 8's expectation.

Run at least twice more to rule out any new test-order flakiness (this session already found and fixed one real Redis-based flakiness source — worth re-confirming stability after a change this size):
```bash
for i in 1 2; do uv run pytest -q 2>&1 | tail -5; done
```

- [ ] **Step 4: Commit**
```bash
git add backend/app/seeds/seed_admin.py
git commit -m "chore(seeds): point seed_admin at the users module"
```

- [ ] **Step 5: note the frontend impact — do not silently fix it as part of this plan**

Two breaking changes ship in this plan that the frontend's API client and i18n error-code maps need to catch up to, separately from this backend-only plan:
- `GET /api/v1/auth/users` → `GET /api/v1/users`; `PATCH /api/v1/auth/users/{id}/status` → `PATCH /api/v1/users/{id}/status`.
- Error codes `auth_user_not_found`/`auth_cannot_block_last_admin`/`auth_cannot_modify_protected_admin` → `users_user_not_found`/`users_cannot_block_last_admin`/`users_cannot_modify_protected_admin`.

Confirm with the user whether to open a follow-up frontend task now or track it separately before merging this branch to a shared environment the frontend depends on.

---

## Self-review notes

- **Spec coverage:** every section of the design spec has a task — module boundary (Tasks 1-5), the 3-way circular-dependency mitigation (Tasks 3-5's leaf-placement + empirical verification steps), the transaction/cache-invalidation ownership fix (Task 2's `invalidate_now`/`UsersApi.invalidate_user`, wired into Task 4's `AuthenticateWithDx`), the confirmed module name/API prefix/env var/error code decisions (Task 1, Task 7).
- **Placeholder scan:** no TODO/TBD; every step has real code, sourced from the actual current file contents read during planning, not reconstructed from memory.
- **Type consistency:** `UsersApi`'s method signatures match between its Task 2 definition and every Task 4/5 consumer (`SyncExternalUser`, `AuthenticateWithDx`, `auth/dependencies.py`'s `get_current_user`, `rbac/public.py`'s `get_assign_role`). `AbstractUsersUnitOfWork.invalidate_now` matches between Task 2's definition, `UsersUnitOfWork`'s implementation, and `UsersApi.invalidate_user`'s one caller.
- **One deliberate behavior change, called out rather than silently shipped:** `get_current_user` raising `NotAuthenticated` instead of `UserNotFound` for a JWT whose subject no longer resolves (Task 4, Step 9) — `UserNotFound` moved to `users` and reaching into it for a session-resolution edge case would misplace the concept; the two error codes were never distinguished by the frontend today anyway (both are terminal "you need to log in again" states).
- **One deliberate scope boundary:** frontend changes are flagged (Task 7, Step 5) but not executed — this plan is backend-only, matching the design spec's stated out-of-scope section.
