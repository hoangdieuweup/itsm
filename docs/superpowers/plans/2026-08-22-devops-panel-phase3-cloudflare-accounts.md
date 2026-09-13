# DevOps Panel Phase 3 — Cloudflare Accounts + 2-layer permission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let designated users create/manage Cloudflare accounts (label + `cf_account_id` + Fernet-encrypted API token) and control, per account, who else can see/edit them, via a new per-resource ACL (`cloudflare_account_managers`) layered on top of the existing global RBAC.

**Architecture:** New backend module `app/modules/cloudflare/` (full fastapi-modular-scaffold tier, including its own `client.py` calling the real Cloudflare v4 REST API — living inside the module, not `app/integrations/`, so a real `.importlinter` facade contract can force every later phase through `cloudflare/public.py`). Two RBAC layers: Layer 1 = ordinary `require_permission("cloudflare_account", "view"|"manage")`; Layer 2 = new `require_account_access(min_level)` dependency checking `cloudflare_account_managers`, bypassed by a new `cloudflare_account:manage_all` permission via a new `RbacApi.has_permission` facade method. New frontend `entities/cloudflare-account` + `modules/cloudflare-accounts`, list + detail routes mirroring `entities/project`/`modules/projects`/`admin/projects/[projectId]` exactly.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, `httpx` (Cloudflare client), `cryptography.fernet` (token encryption), pytest + testcontainers (Postgres). Next.js App Router, TanStack Query, Zod, next-intl.

**Spec:** The "Phase 3 — Detailed Plan: Cloudflare Accounts + 2-layer permission" section of `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md` (approved this session) — read that section in full; it is the source of truth this plan implements task-by-task. Also: `docs/tasks/devops-control-panel-schema.md` §2 (ERD) and §8 (2-layer permission design, Vietnamese) and `docs/tasks/cloudflare-api-reference.md` §1 (Zones).

## Global Constraints

- Router thinness (rule #10): `router.py` only translates HTTP → use-case call. The PATCH-account body-dependent OWNER-vs-EDITOR level check happens **inside** `UpdateCloudflareAccount`'s use case, never in the router or stapled onto a `Depends` factory.
- No bare constants (rule #16): every audit action string goes through `CloudflareAccountAuditActions` (a `StrEnum` in `cloudflare/constants.py`) — never a raw string literal in a service.
- No proxy re-exports: frontend imports go directly from `@/entities/cloudflare-account`, never through a re-export shim in `modules/`.
- Every Layer-2-gated route (`require_account_access`) also requires its matching Layer-1 permission (`view` for reads, `manage` for writes) — Layer 2 only *narrows* Layer 1, it never independently grants capability.
- `blocks_last_owner_removal` guards **both** `DELETE .../managers/{user_id}` and `PATCH .../managers/{user_id}` (a downgrade has the same effect as a delete). `manage_all` holders get **zero** exemption from this guard — mirrors `RbacRules.blocks_last_admin_removal`'s unconditional semantics.
- Secrets: `CloudflareAccountRead` never includes `api_token` in any form. The `reveal-token` audit log entry's `message`/`payload` must never contain the decrypted token value — only `{account_id}` and the actor.
- `cloudflare/client.py`'s `test_connection` must treat both an HTTP error status AND an HTTP-200 response whose JSON body has `"success": false` (Cloudflare's v4 API envelope) as a failed connection — a status-only check (like `dx_core/client.py`'s simpler `_raise_for_upstream_error`) is insufficient here.
- Alembic: new revision, `down_revision = 'b6dd7c2f4a91'` (confirmed current head — do not branch off anything else).
- `.importlinter`'s `<name>-facade` contracts are hardcoded `source_modules` lists that do **not** auto-extend (unlike `scripts/check_module_boundaries.py`) — both a new `cloudflare-facade` stanza AND edits to the existing `rbac-facade`/`audit-facade` stanzas' `source_modules` lists are required.
- Test DB: **never** run any manual/smoke verification against `business-chatbot-postgres` (the live DB behind `itsm.agentsplatform.cloud`) — use the local testcontainer / dedicated local Postgres+Mongo stack only.

---

## Task 1: Alembic migration for `cloudflare_accounts` + `cloudflare_account_managers`

**Files:**
- Create: `backend/alembic/versions/<new_revision>_create_cloudflare_accounts_schema.py`

**Interfaces:**
- Produces: `cloudflare_accounts` table (`id` UUID PK, `label` varchar(255), `cf_account_id` varchar(64), `api_token` text, `created_by` UUID FK→`users.id` SET NULL nullable, `created_at`/`updated_at` timestamptz), `cloudflare_account_managers` table (`cloudflare_account_id` UUID FK→`cloudflare_accounts.id` CASCADE, `user_id` UUID FK→`users.id` CASCADE, composite PK on both, `access_level` enum(`owner`,`editor`,`viewer`, non-native), `created_at` timestamptz).

- [ ] **Step 1: Confirm the current Alembic head**

Run: `cd backend && uv run alembic heads`
Expected: `b6dd7c2f4a91 (head)` — this is the `down_revision` for the new file.

- [ ] **Step 2: Write the migration**

```python
"""create_cloudflare_accounts_schema

Revision ID: c1a3f9d2b8e4
Revises: b6dd7c2f4a91
Create Date: 2026-08-22 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c1a3f9d2b8e4'
down_revision = 'b6dd7c2f4a91'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cloudflare_accounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('cf_account_id', sa.String(length=64), nullable=False),
    sa.Column('api_token', sa.Text(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['created_by'], ['users.id'], name=op.f('cloudflare_accounts_created_by_fkey'), ondelete='SET NULL'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('cloudflare_accounts_pkey'))
    )
    op.create_table('cloudflare_account_managers',
    sa.Column('cloudflare_account_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column(
        'access_level',
        sa.Enum('owner', 'editor', 'viewer', name='cloudflareaccessLevel', native_enum=False),
        nullable=False,
    ),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['cloudflare_account_id'], ['cloudflare_accounts.id'],
        name=op.f('cloudflare_account_managers_cloudflare_account_id_fkey'), ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['user_id'], ['users.id'], name=op.f('cloudflare_account_managers_user_id_fkey'), ondelete='CASCADE'
    ),
    sa.PrimaryKeyConstraint('cloudflare_account_id', 'user_id', name=op.f('cloudflare_account_managers_pkey'))
    )
    op.create_index(
        op.f('cloudflare_account_managers_user_id_idx'), 'cloudflare_account_managers', ['user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('cloudflare_account_managers_user_id_idx'), table_name='cloudflare_account_managers')
    op.drop_table('cloudflare_account_managers')
    op.drop_table('cloudflare_accounts')
```

- [ ] **Step 3: Apply against the local test DB and verify**

Run: `cd backend && uv run alembic upgrade head` (against your local dev/test Postgres — never `business-chatbot-postgres`)
Expected: both tables exist; `uv run alembic downgrade -1 && uv run alembic upgrade head` round-trips cleanly.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/c1a3f9d2b8e4_create_cloudflare_accounts_schema.py
git commit -m "feat(cloudflare): add cloudflare_accounts and cloudflare_account_managers migration"
```

---

## Task 2: `constants.py` + `models.py`

**Files:**
- Create: `backend/app/modules/cloudflare/__init__.py` (empty)
- Create: `backend/app/modules/cloudflare/constants.py`
- Create: `backend/app/modules/cloudflare/models.py`

**Interfaces:**
- Produces: `AccessLevel(StrEnum)` with values `OWNER="owner"`, `EDITOR="editor"`, `VIEWER="viewer"`; `ACCESS_LEVEL_RANK: dict[AccessLevel, int]`; `CloudflareAccountLimits`, `CloudflareAccountsCacheKeys`, `ErrorCode(StrEnum)`, `CloudflareAccountAuditActions(StrEnum)`; ORM classes `CloudflareAccount`, `CloudflareAccountManager`.

- [ ] **Step 1: Write `constants.py`**

```python
"""Constants and enums owned by the cloudflare module."""

from enum import StrEnum


class CloudflareAccountLimits:
    """Numeric limits owned by the cloudflare module."""

    MAX_LABEL_LENGTH = 255
    MAX_CF_ACCOUNT_ID_LENGTH = 64


class AccessLevel(StrEnum):
    """Per-account access level, ranked VIEWER < EDITOR < OWNER. See ACCESS_LEVEL_RANK."""

    VIEWER = "viewer"
    EDITOR = "editor"
    OWNER = "owner"


ACCESS_LEVEL_RANK: dict[AccessLevel, int] = {
    AccessLevel.VIEWER: 0,
    AccessLevel.EDITOR: 1,
    AccessLevel.OWNER: 2,
}


class CloudflareAccountsCacheKeys:
    """Cache identity owned by the cloudflare module. See references/caching.md."""

    ACCOUNT_ENTITY = "cloudflare_account"
    TTL_SECONDS = 300


class ErrorCode(StrEnum):
    """Stable error codes returned to clients by this module."""

    ACCOUNT_NOT_FOUND = "cloudflare_account_not_found"
    MANAGER_NOT_FOUND = "cloudflare_account_manager_not_found"
    INVALID_TOKEN = "cloudflare_invalid_token"
    API_UNAVAILABLE = "cloudflare_api_unavailable"
    INSUFFICIENT_ACCESS = "cloudflare_insufficient_account_access"
    LAST_OWNER_REMOVAL_BLOCKED = "cloudflare_last_owner_removal_blocked"


class CloudflareAccountAuditActions(StrEnum):
    """Action identifiers this module writes via audit.log_event. Centralized
    so the same string is never typo'd or drifted across call sites — audit
    itself is domain-agnostic and only ever sees whatever string is passed."""

    ACCOUNT_CREATED = "CLOUDFLARE_ACCOUNT_CREATED"
    ACCOUNT_UPDATED = "CLOUDFLARE_ACCOUNT_UPDATED"
    ACCOUNT_DELETED = "CLOUDFLARE_ACCOUNT_DELETED"
    TOKEN_REVEALED = "CLOUDFLARE_ACCOUNT_TOKEN_REVEALED"
    MANAGER_ASSIGNED = "CLOUDFLARE_ACCOUNT_MANAGER_ASSIGNED"
    MANAGER_UPDATED = "CLOUDFLARE_ACCOUNT_MANAGER_UPDATED"
    MANAGER_REMOVED = "CLOUDFLARE_ACCOUNT_MANAGER_REMOVED"
```

- [ ] **Step 2: Write `models.py`**

```python
"""ORM models owned by the cloudflare module. No other module may query these tables."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountLimits


class CloudflareAccount(Base):
    """A Cloudflare account credential, potentially shared across many projects."""

    __tablename__ = "cloudflare_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(CloudflareAccountLimits.MAX_LABEL_LENGTH))
    cf_account_id: Mapped[str] = mapped_column(String(CloudflareAccountLimits.MAX_CF_ACCOUNT_ID_LENGTH))
    api_token: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CloudflareAccountManager(Base):
    """Per-account ACL row: one user's access_level on one cloudflare_account."""

    __tablename__ = "cloudflare_account_managers"

    cloudflare_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cloudflare_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    access_level: Mapped[AccessLevel] = mapped_column(Enum(AccessLevel, native_enum=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 3: Verify the models import cleanly and match the migration**

Run: `cd backend && uv run python -c "from app.modules.cloudflare.models import CloudflareAccount, CloudflareAccountManager; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/cloudflare/__init__.py backend/app/modules/cloudflare/constants.py backend/app/modules/cloudflare/models.py
git commit -m "feat(cloudflare): add module constants and ORM models"
```

---

## Task 3: `schemas.py` + `exceptions.py`

**Files:**
- Create: `backend/app/modules/cloudflare/schemas.py`
- Create: `backend/app/modules/cloudflare/exceptions.py`

**Interfaces:**
- Consumes: `AccessLevel`, `ErrorCode` from Task 2's `constants.py`; `CustomModel`/`FrozenModel` from `app/core/models.py`; `NotFoundError`/`ConflictError`/`ForbiddenError`/`ValidationFailedError`/`IntegrationError` from `app/core/exceptions.py`.
- Produces: `CloudflareAccountRead`, `CloudflareAccountCreate`, `CloudflareAccountUpdate`, `CloudflareAccountManagerRead`, `CloudflareAccountManagerAssign`, `CloudflareAccountManagerUpdate`, `TokenRevealResponse`, `AccountAccessGrant` schemas; `CloudflareAccountNotFound`, `CloudflareAccountManagerNotFound`, `InvalidCloudflareToken`, `CloudflareApiUnavailable`, `InsufficientAccountAccess`, `LastOwnerRemovalBlocked` exceptions. `AccountAccessGrant` lives here rather than in `dependencies.py` specifically to avoid a Task 8/Task 10 circular import — see that class's own docstring.

- [ ] **Step 1: Write `schemas.py`**

```python
"""Schemas for the cloudflare module."""

from datetime import datetime
from uuid import UUID

from app.core.models import CustomModel, FrozenModel
from app.modules.cloudflare.constants import AccessLevel
from app.modules.users.public import UserRead


class CloudflareAccountRead(FrozenModel):
    """Representation safe to round trip through the cache. Never includes api_token."""

    id: UUID
    label: str
    cf_account_id: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class CloudflareAccountCreate(CustomModel):
    """Request body for POST /cloudflare-accounts."""

    label: str
    cf_account_id: str
    api_token: str


class CloudflareAccountUpdate(CustomModel):
    """Request body for PATCH /cloudflare-accounts/{id}. None means unchanged.
    Providing api_token means "rotate the token" and requires OWNER — see
    UpdateCloudflareAccount's use case."""

    label: str | None = None
    api_token: str | None = None


class CloudflareAccountManagerRead(FrozenModel):
    """One manager row, enriched with the target user's email/name (resolved
    via UsersApi in the service layer — the repository only knows user_id)."""

    user_id: UUID
    email: str
    name: str
    access_level: AccessLevel
    created_at: datetime


class CloudflareAccountManagerAssign(CustomModel):
    """Request body for POST /cloudflare-accounts/{id}/managers."""

    user_id: UUID
    access_level: AccessLevel


class CloudflareAccountManagerUpdate(CustomModel):
    """Request body for PATCH /cloudflare-accounts/{id}/managers/{user_id}."""

    access_level: AccessLevel


class TokenRevealResponse(FrozenModel):
    """Response body for POST /cloudflare-accounts/{id}/reveal-token. Never cached."""

    api_token: str


class AccountAccessGrant(FrozenModel):
    """The resolved outcome of a Layer-2 require_account_access check: which
    user, and at what access_level — None means they passed via the
    cloudflare_account:manage_all Layer-1 bypass, which
    CloudflareAccountRules.satisfies_level treats as always-sufficient.

    Lives here (not in dependencies.py, where it's constructed) so both
    dependencies.py AND services/update_account.py can import it without a
    cycle — dependencies.py imports service classes to build its provider
    functions, so a service can never import dependencies.py back."""

    user: UserRead
    held_level: AccessLevel | None
```

- [ ] **Step 2: Write `exceptions.py`**

```python
"""Errors owned by the cloudflare module."""

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationFailedError,
)
from app.modules.cloudflare.constants import ErrorCode


class CloudflareAccountNotFound(NotFoundError):
    """Raised when no cloudflare account matches the requested id."""

    code = ErrorCode.ACCOUNT_NOT_FOUND
    message = "Cloudflare account not found"


class CloudflareAccountManagerNotFound(NotFoundError):
    """Raised when no manager row matches the requested (account_id, user_id)."""

    code = ErrorCode.MANAGER_NOT_FOUND
    message = "Cloudflare account manager not found"


class InvalidCloudflareToken(ValidationFailedError):
    """Raised when Cloudflare rejects the provided API token (bad token, or a
    200 response with the v4 envelope's success=false)."""

    code = ErrorCode.INVALID_TOKEN
    message = "Cloudflare rejected the provided API token"


class CloudflareApiUnavailable(IntegrationError):
    """Raised when the Cloudflare API cannot be reached or returns a server error."""

    code = ErrorCode.API_UNAVAILABLE
    message = "Cloudflare API unavailable"


class InsufficientAccountAccess(ForbiddenError):
    """Raised when the caller's per-account access_level does not satisfy the
    level required for the requested action."""

    code = ErrorCode.INSUFFICIENT_ACCESS
    message = "Insufficient access level on this Cloudflare account"


class LastOwnerRemovalBlocked(ConflictError):
    """Raised when removing or downgrading a manager row would leave zero
    OWNERs on the account."""

    code = ErrorCode.LAST_OWNER_REMOVAL_BLOCKED
    message = "Cannot remove or downgrade the last owner of this account"
```

- [ ] **Step 3: Verify imports**

Run: `cd backend && uv run python -c "from app.modules.cloudflare.schemas import CloudflareAccountRead; from app.modules.cloudflare.exceptions import CloudflareAccountNotFound; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/cloudflare/schemas.py backend/app/modules/cloudflare/exceptions.py
git commit -m "feat(cloudflare): add schemas and exceptions"
```

---

## Task 4: `rules.py` (pure business rules, unit tested)

**Files:**
- Create: `backend/app/modules/cloudflare/rules.py`
- Test: `backend/tests/cloudflare/__init__.py` (empty)
- Test: `backend/tests/cloudflare/test_rules.py`

**Interfaces:**
- Consumes: `AccessLevel`, `ACCESS_LEVEL_RANK` from `cloudflare/constants.py`; `rule` marker from `app.core.base.markers`.
- Produces: `CloudflareAccountRules.satisfies_level(held: AccessLevel | None, required: AccessLevel) -> bool`, `CloudflareAccountRules.required_level_for_update(rotates_token: bool) -> AccessLevel`, `CloudflareAccountRules.blocks_last_owner_removal(access_level: AccessLevel, remaining_owner_grants: int) -> bool`. Every later service task calls these exact names/signatures.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for app.modules.cloudflare.rules — pure functions, no I/O."""

from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.rules import CloudflareAccountRules


class TestSatisfiesLevel:
    def test_owner_satisfies_viewer(self) -> None:
        assert CloudflareAccountRules.satisfies_level(AccessLevel.OWNER, AccessLevel.VIEWER) is True

    def test_editor_satisfies_editor(self) -> None:
        assert CloudflareAccountRules.satisfies_level(AccessLevel.EDITOR, AccessLevel.EDITOR) is True

    def test_viewer_does_not_satisfy_owner(self) -> None:
        assert CloudflareAccountRules.satisfies_level(AccessLevel.VIEWER, AccessLevel.OWNER) is False

    def test_none_always_satisfies(self) -> None:
        """None means the caller passed via the manage_all Layer-1 bypass."""
        assert CloudflareAccountRules.satisfies_level(None, AccessLevel.OWNER) is True


class TestRequiredLevelForUpdate:
    def test_rotating_token_requires_owner(self) -> None:
        assert CloudflareAccountRules.required_level_for_update(rotates_token=True) is AccessLevel.OWNER

    def test_label_only_requires_editor(self) -> None:
        assert CloudflareAccountRules.required_level_for_update(rotates_token=False) is AccessLevel.EDITOR


class TestBlocksLastOwnerRemoval:
    def test_blocks_when_only_owner_remains(self) -> None:
        assert CloudflareAccountRules.blocks_last_owner_removal(AccessLevel.OWNER, 1) is True

    def test_allows_when_multiple_owners_remain(self) -> None:
        assert CloudflareAccountRules.blocks_last_owner_removal(AccessLevel.OWNER, 2) is False

    def test_allows_removing_a_non_owner(self) -> None:
        assert CloudflareAccountRules.blocks_last_owner_removal(AccessLevel.EDITOR, 1) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.cloudflare.rules'`

- [ ] **Step 3: Write `rules.py`**

```python
"""Business rules for the cloudflare module.

Everything here is a pure decision: no I/O, no framework, no database.
"""

from app.core.base.markers import rule
from app.modules.cloudflare.constants import ACCESS_LEVEL_RANK, AccessLevel


class CloudflareAccountRules:
    """Every business decision about a cloudflare account or its per-account ACL."""

    @staticmethod
    @rule
    def satisfies_level(held: AccessLevel | None, required: AccessLevel) -> bool:
        """True if held meets or exceeds required. held=None means the caller
        passed the check via the manage_all Layer-1 bypass — always satisfies,
        since manage_all is a strictly higher grant than any per-account row."""
        if held is None:
            return True
        return ACCESS_LEVEL_RANK[held] >= ACCESS_LEVEL_RANK[required]

    @staticmethod
    @rule
    def required_level_for_update(rotates_token: bool) -> AccessLevel:
        """Rotating the token is equivalent to re-proving ownership of the
        credential, so it needs OWNER. Any other field-only edit needs EDITOR."""
        return AccessLevel.OWNER if rotates_token else AccessLevel.EDITOR

    @staticmethod
    @rule
    def blocks_last_owner_removal(access_level: AccessLevel, remaining_owner_grants: int) -> bool:
        """True when removing or downgrading this grant would leave zero
        OWNERs able to manage the account. remaining_owner_grants counts
        OWNER-level rows *including* the one about to be changed — mirrors
        RbacRules.blocks_last_admin_removal's exact convention. Applies
        unconditionally: manage_all holders get no exemption, since exempting
        them would let a superuser strip the last OWNER and permanently
        escalate routine account admin into a superuser-only workflow."""
        return access_level == AccessLevel.OWNER and remaining_owner_grants <= 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_rules.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/cloudflare/__init__.py backend/tests/cloudflare/test_rules.py backend/app/modules/cloudflare/rules.py
git commit -m "feat(cloudflare): add CloudflareAccountRules with unit tests"
```

---

## Task 5: `config.py` + `client.py` (Cloudflare API client, unit tested with a fake transport)

**Files:**
- Create: `backend/app/modules/cloudflare/config.py`
- Create: `backend/app/modules/cloudflare/client.py`
- Test: `backend/tests/cloudflare/test_client.py`

**Interfaces:**
- Consumes: `integration` marker from `app.core.base.markers`; `CloudflareApiUnavailable`, `InvalidCloudflareToken` from Task 3's `exceptions.py`.
- Produces: `cloudflare_settings: CloudflareConfig` (module-level singleton, `API_BASE_URL`, `FERNET_KEY`, `HTTP_TIMEOUT_SECONDS`); `CloudflareClient(transport: httpx.AsyncBaseTransport | None = None)` with `async def test_connection(self, *, cf_account_id: str, api_token: str) -> None`. Later tasks (Task 6 `dependencies.py`, all services) construct `CloudflareClient()` with no args in production and inject a fake `httpx.MockTransport` only in tests.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for app.modules.cloudflare.client — no real network calls, a
fake httpx transport stands in for Cloudflare's API."""

import httpx
import pytest

from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.exceptions import CloudflareApiUnavailable, InvalidCloudflareToken


class TestTestConnection:
    async def test_succeeds_on_200_with_success_true(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["account.id"] == "acc1"
            assert request.headers["authorization"] == "Bearer good-token"
            return httpx.Response(200, json={"success": True, "result": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        await client.test_connection(cf_account_id="acc1", api_token="good-token")

    async def test_raises_invalid_token_on_401(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"success": False, "errors": [{"message": "bad token"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidCloudflareToken):
            await client.test_connection(cf_account_id="acc1", api_token="bad")

    async def test_raises_invalid_token_on_200_with_success_false(self) -> None:
        """Cloudflare's v4 API can return HTTP 200 with success=false — status
        alone is not enough to decide whether the token was accepted."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "errors": [{"message": "insufficient scope"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidCloudflareToken):
            await client.test_connection(cf_account_id="acc1", api_token="wrong-scope")

    async def test_raises_unavailable_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.test_connection(cf_account_id="acc1", api_token="x")

    async def test_raises_unavailable_on_500(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"success": False, "errors": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.test_connection(cf_account_id="acc1", api_token="x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.cloudflare.client'`

- [ ] **Step 3: Write `config.py`**

```python
"""Settings owned by the cloudflare module."""

from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class CloudflareConfig(BaseSettings):
    """Environment driven settings for the cloudflare module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CLOUDFLARE__", extra="ignore")

    API_BASE_URL: HttpUrl = HttpUrl("https://api.cloudflare.com/client/v4")
    # Fernet key encrypting CloudflareAccount.api_token at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""
    HTTP_TIMEOUT_SECONDS: float = 10.0


cloudflare_settings = CloudflareConfig()
```

- [ ] **Step 4: Write `client.py`**

```python
"""Cloudflare REST API client. HTTP only — no database.

Lives inside app/modules/cloudflare/ rather than a new app/integrations/
package: unlike dx_core (one consumer, no facade contract), this client
will gain many consumers across Phases 4/5/6/9 (DNS, Tunnels, log viewer,
alerting) — keeping it inside the module lets a real .importlinter
cloudflare-facade contract force every one of them through
cloudflare/public.py instead of reaching in directly.
"""

import httpx

from app.core.base.markers import integration
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareApiUnavailable, InvalidCloudflareToken


class CloudflareClient:
    """Talks to the Cloudflare REST API. One instance per request, built in
    dependencies.py. `transport` is injectable only for tests — production
    code always constructs CloudflareClient() with no arguments."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @integration
    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        """GET /zones?account.id=<cf_account_id>. Raises InvalidCloudflareToken
        when Cloudflare rejects the token — either via HTTP 4xx, or via an
        HTTP 200 whose v4 envelope has success=false (Cloudflare wraps every
        response in {success, errors, result} and does not always signal a
        bad/under-scoped token through HTTP status alone). Raises
        CloudflareApiUnavailable on transport failure or a 5xx response."""
        try:
            async with httpx.AsyncClient(
                base_url=str(cloudflare_settings.API_BASE_URL), transport=self._transport
            ) as client:
                response = await client.get(
                    "/zones",
                    params={"account.id": cf_account_id},
                    headers={"Authorization": f"Bearer {api_token}"},
                    timeout=cloudflare_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise CloudflareApiUnavailable() from exc

        if response.status_code in (400, 401, 403):
            raise InvalidCloudflareToken()
        if response.is_error:
            raise CloudflareApiUnavailable(status_code=response.status_code)
        if not response.json().get("success", False):
            raise InvalidCloudflareToken()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/cloudflare/config.py backend/app/modules/cloudflare/client.py backend/tests/cloudflare/test_client.py
git commit -m "feat(cloudflare): add CloudflareClient with envelope-aware test_connection"
```

---

## Task 6: `repository.py` + `uow.py`

**Files:**
- Create: `backend/app/modules/cloudflare/repository.py`
- Create: `backend/app/modules/cloudflare/uow.py`

**Interfaces:**
- Consumes: `database`/`helper` markers; `AbstractRepository[EntityT, IdT]` from `app.core.base.repository`; `AbstractUnitOfWork` from `app.core.base.uow`; `CacheClient` from `app.integrations.cache.client`; `CloudflareAccountRead` from Task 3.
- Produces:
  - `AbstractCloudflareAccountRepository` — `create(*, label, cf_account_id, api_token, created_by) -> CloudflareAccountRead`, `update(account_id, *, label, api_token) -> CloudflareAccountRead`, `delete(account_id) -> None`, `get_token_ciphertext(account_id) -> str | None` (raw `api_token` column, still Fernet-ciphertext — decryption happens in the service layer, never in the repository).
  - `AbstractCloudflareAccountManagerRepository` — `get_for_user(account_id, user_id) -> CloudflareAccountManagerRow | None`, `list_for_account(account_id) -> list[CloudflareAccountManagerRow]`, `list_for_user(user_id) -> list[CloudflareAccountManagerRow]` (used by the filtered `GET /cloudflare-accounts` list), `count_owners(account_id) -> int`, `upsert(account_id, user_id, access_level) -> CloudflareAccountManagerRow`, `remove(account_id, user_id) -> None`. `CloudflareAccountManagerRow` is a small `FrozenModel` (`account_id`, `user_id`, `access_level`, `created_at`) — deliberately NOT `CloudflareAccountManagerRead` (which needs email/name enrichment the repository cannot do).
  - `AbstractCloudflareUnitOfWork(accounts, account_managers)` + concrete `CloudflareUnitOfWork`, mirrors `ProjectsUnitOfWork` (cache-aside invalidation via `mark_stale`, commit-then-invalidate ordering).

- [ ] **Step 1: Write `repository.py`**

```python
"""Single access path to the cloudflare_accounts and cloudflare_account_managers tables."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.core.models import FrozenModel
from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountsCacheKeys
from app.modules.cloudflare.models import CloudflareAccount, CloudflareAccountManager
from app.modules.cloudflare.schemas import CloudflareAccountRead


class CloudflareAccountManagerRow(FrozenModel):
    """Raw manager row — no email/name (the repository has no cross-module
    knowledge of users; enrichment happens in the service layer via UsersApi)."""

    cloudflare_account_id: UUID
    user_id: UUID
    access_level: AccessLevel
    created_at: object


class AbstractCloudflareAccountRepository(AbstractRepository[CloudflareAccountRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def create(
        self, *, label: str, cf_account_id: str, api_token: str, created_by: UUID | None
    ) -> CloudflareAccountRead:
        """Create a new account. api_token must already be Fernet-ciphertext."""
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, account_id: UUID, *, label: str | None, api_token: str | None
    ) -> CloudflareAccountRead:
        """Rename and/or rotate the token. api_token, if given, must already be ciphertext."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, account_id: UUID) -> None:
        """Delete an account. Its manager rows cascade at the DB level."""
        raise NotImplementedError

    @abstractmethod
    async def get_token_ciphertext(self, account_id: UUID) -> str | None:
        """Return the raw (still-encrypted) api_token column, or None if the
        account doesn't exist. Bypasses the cache-aside CloudflareAccountRead
        entirely — a secret never enters the cache."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_ids(self, account_ids: list[UUID]) -> list[CloudflareAccountRead]:
        """Return every account whose id is in account_ids, in no particular
        order — backs the filtered GET /cloudflare-accounts list."""
        raise NotImplementedError


class CloudflareAccountRepository(AbstractCloudflareAccountRepository):
    """SQLAlchemy implementation. Every read/write of cloudflare_accounts goes through this class."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache

    @database
    async def get_by_id(self, entity_id: UUID) -> CloudflareAccountRead | None:
        """Return one account, or None when it does not exist. Cache-aside."""
        return await self._cache.get_or_load(
            CloudflareAccountsCacheKeys.ACCOUNT_ENTITY, entity_id, CloudflareAccountRead,
            lambda: self._load_by_id(entity_id),
        )

    @helper
    async def _load_by_id(self, entity_id: UUID) -> CloudflareAccountRead | None:
        """Direct database read backing get_by_id's cache-aside loader."""
        row = await self._session.scalar(select(CloudflareAccount).where(CloudflareAccount.id == entity_id))
        return CloudflareAccountRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountRead], int]:
        """Required by AbstractRepository; the router never lists unfiltered —
        see list_for_ids, which backs the actual GET /cloudflare-accounts route."""
        rows = await self._session.scalars(
            select(CloudflareAccount).order_by(CloudflareAccount.id).limit(limit).offset(offset)
        )
        items = [CloudflareAccountRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(CloudflareAccount))
        return items, total or 0

    @database
    async def list_for_ids(self, account_ids: list[UUID]) -> list[CloudflareAccountRead]:
        """Return every account whose id is in account_ids."""
        if not account_ids:
            return []
        rows = await self._session.scalars(
            select(CloudflareAccount).where(CloudflareAccount.id.in_(account_ids))
        )
        return [CloudflareAccountRead.model_validate(row) for row in rows]

    @database
    async def create(
        self, *, label: str, cf_account_id: str, api_token: str, created_by: UUID | None
    ) -> CloudflareAccountRead:
        """Create a new account."""
        row = CloudflareAccount(
            label=label, cf_account_id=cf_account_id, api_token=api_token, created_by=created_by
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareAccountRead.model_validate(row)

    @database
    async def update(
        self, account_id: UUID, *, label: str | None, api_token: str | None
    ) -> CloudflareAccountRead:
        """Rename and/or rotate the token. Caller must confirm account_id exists first."""
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None:
            raise ValueError(f"cloudflare account {account_id} does not exist")
        if label is not None:
            row.label = label
        if api_token is not None:
            row.api_token = api_token
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareAccountRead.model_validate(row)

    @database
    async def delete(self, account_id: UUID) -> None:
        """Delete an account. Caller must confirm account_id exists first."""
        row = await self._session.get(CloudflareAccount, account_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def get_token_ciphertext(self, account_id: UUID) -> str | None:
        """Return the raw api_token column, still Fernet-ciphertext. Never cached."""
        row = await self._session.get(CloudflareAccount, account_id)
        return row.api_token if row is not None else None


class AbstractCloudflareAccountManagerRepository(AbstractRepository[CloudflareAccountManagerRow, tuple]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def get_for_user(self, account_id: UUID, user_id: UUID) -> CloudflareAccountManagerRow | None:
        """Look up one user's manager row on one account, or None if they have no access."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_account(self, account_id: UUID) -> list[CloudflareAccountManagerRow]:
        """Return every manager row for one account."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_user(self, user_id: UUID) -> list[CloudflareAccountManagerRow]:
        """Return every manager row for one user — backs the filtered account list."""
        raise NotImplementedError

    @abstractmethod
    async def count_owners(self, account_id: UUID) -> int:
        """Count OWNER-level rows on one account."""
        raise NotImplementedError

    @abstractmethod
    async def upsert(
        self, account_id: UUID, user_id: UUID, access_level: AccessLevel
    ) -> CloudflareAccountManagerRow:
        """Insert or update a manager row."""
        raise NotImplementedError

    @abstractmethod
    async def remove(self, account_id: UUID, user_id: UUID) -> None:
        """Delete a manager row. No-op if it doesn't exist."""
        raise NotImplementedError


class CloudflareAccountManagerRepository(AbstractCloudflareAccountManagerRepository):
    """SQLAlchemy implementation. Every read/write of cloudflare_account_managers goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: tuple) -> CloudflareAccountManagerRow | None:
        """Required by AbstractRepository; callers use get_for_user instead."""
        account_id, user_id = entity_id
        return await self.get_for_user(account_id, user_id)

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountManagerRow], int]:
        """Required by AbstractRepository; manager rows are listed per-account in practice."""
        rows = await self._session.scalars(select(CloudflareAccountManager).limit(limit).offset(offset))
        items = [CloudflareAccountManagerRow.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(CloudflareAccountManager))
        return items, total or 0

    @database
    async def get_for_user(self, account_id: UUID, user_id: UUID) -> CloudflareAccountManagerRow | None:
        """Look up one user's manager row on one account."""
        row = await self._session.get(CloudflareAccountManager, (account_id, user_id))
        return CloudflareAccountManagerRow.model_validate(row) if row else None

    @database
    async def list_for_account(self, account_id: UUID) -> list[CloudflareAccountManagerRow]:
        """Return every manager row for one account."""
        rows = await self._session.scalars(
            select(CloudflareAccountManager)
            .where(CloudflareAccountManager.cloudflare_account_id == account_id)
            .order_by(CloudflareAccountManager.created_at)
        )
        return [CloudflareAccountManagerRow.model_validate(row) for row in rows]

    @database
    async def list_for_user(self, user_id: UUID) -> list[CloudflareAccountManagerRow]:
        """Return every manager row for one user."""
        rows = await self._session.scalars(
            select(CloudflareAccountManager).where(CloudflareAccountManager.user_id == user_id)
        )
        return [CloudflareAccountManagerRow.model_validate(row) for row in rows]

    @database
    async def count_owners(self, account_id: UUID) -> int:
        """Count OWNER-level rows on one account."""
        count = await self._session.scalar(
            select(func.count()).select_from(CloudflareAccountManager).where(
                CloudflareAccountManager.cloudflare_account_id == account_id,
                CloudflareAccountManager.access_level == AccessLevel.OWNER,
            )
        )
        return count or 0

    @database
    async def upsert(
        self, account_id: UUID, user_id: UUID, access_level: AccessLevel
    ) -> CloudflareAccountManagerRow:
        """Insert or update a manager row."""
        row = await self._session.get(CloudflareAccountManager, (account_id, user_id))
        if row is None:
            row = CloudflareAccountManager(
                cloudflare_account_id=account_id, user_id=user_id, access_level=access_level
            )
            self._session.add(row)
        else:
            row.access_level = access_level
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareAccountManagerRow.model_validate(row)

    @database
    async def remove(self, account_id: UUID, user_id: UUID) -> None:
        """Delete a manager row. No-op if it doesn't exist."""
        row = await self._session.get(CloudflareAccountManager, (account_id, user_id))
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
```

- [ ] **Step 2: Write `uow.py`**

```python
"""Transaction boundary for the cloudflare module."""

import logging
from abc import abstractmethod
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractUnitOfWork
from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    CloudflareAccountManagerRepository,
    CloudflareAccountRepository,
)

logger = logging.getLogger(__name__)


class AbstractCloudflareUnitOfWork(AbstractUnitOfWork):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    accounts: AbstractCloudflareAccountRepository
    account_managers: AbstractCloudflareAccountManagerRepository

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        """Queue a cache entity for invalidation once THIS uow's own commit() runs."""
        raise NotImplementedError


class CloudflareUnitOfWork(AbstractCloudflareUnitOfWork):
    """Owns the transaction for the cloudflare module's tables."""

    def __init__(self, session: AsyncSession, cache: CacheClient) -> None:
        self._session = session
        self._cache = cache
        self._stale: list[tuple[str, UUID]] = []
        self.accounts = CloudflareAccountRepository(session, cache)
        self.account_managers = CloudflareAccountManagerRepository(session)

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

    @database
    async def commit(self) -> None:
        """Commit the transaction, then invalidate every queued cache entity —
        strictly after the database commit, per references/caching.md#order-of-operations."""
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction and drop any queued invalidation."""
        await self._session.rollback()
        self._stale.clear()
        logger.warning("cloudflare unit of work rolled back")
```

- [ ] **Step 3: Verify imports**

Run: `cd backend && uv run python -c "from app.modules.cloudflare.uow import CloudflareUnitOfWork; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/cloudflare/repository.py backend/app/modules/cloudflare/uow.py
git commit -m "feat(cloudflare): add repository and unit of work"
```

---

## Task 7: `RbacApi.has_permission` + `RbacPermissionCatalog` append

**Files:**
- Modify: `backend/app/modules/rbac/public.py`
- Modify: `backend/app/modules/rbac/constants.py`

**Interfaces:**
- Consumes: existing `uow.user_roles.user_has_permission(user_id, resource, action) -> bool` (`backend/app/modules/rbac/repository.py:300`, already used internally by `require_permission`'s closure — no new repository method needed).
- Produces: `RbacApi.has_permission(self, user_id: UUID, resource: str, action: str) -> bool` (added to `__all__`), 3 new catalog tuples: `("cloudflare_account", "manage", "permissions.cloudflare_account.manage")`, `("cloudflare_account", "view", "permissions.cloudflare_account.view")`, `("cloudflare_account", "manage_all", "permissions.cloudflare_account.manage_all")`. Task 8's `require_account_access` dependency calls `RbacApi.has_permission(user_id, "cloudflare_account", "manage_all")` for the Layer-1 bypass.

- [ ] **Step 1: Add the 3 tuples to `RbacPermissionCatalog.CATALOG`**

In `backend/app/modules/rbac/constants.py`, append after the existing `("audit_log", "read", "permissions.audit_log.read"),` line:

```python
        ("cloudflare_account", "manage", "permissions.cloudflare_account.manage"),
        ("cloudflare_account", "view", "permissions.cloudflare_account.view"),
        ("cloudflare_account", "manage_all", "permissions.cloudflare_account.manage_all"),
```

- [ ] **Step 2: Add `has_permission` to `RbacApi`**

In `backend/app/modules/rbac/public.py`, add `"has_permission"` to `__all__`, and add this method to the `RbacApi` class (right after `is_last_admin`):

```python
    @facade
    async def has_permission(self, user_id: UUID, resource: str, action: str) -> bool:
        """Direct boolean permission check for a module that needs to compose
        it with a SECOND, module-owned authorization check (e.g. cloudflare's
        manage_all bypass inside require_account_access) — require_permission
        is a 403-raising route dependency, not reusable as a plain boolean."""
        return await self._uow.user_roles.user_has_permission(user_id, resource, action)
```

- [ ] **Step 3: Verify existing rbac tests still pass and re-seed**

Run: `cd backend && uv run pytest tests/rbac -v`
Expected: PASS, unchanged (purely additive change).

Run: `cd backend && uv run python -m app.seeds.seed_rbac` (against your local dev DB)
Expected: 3 new permission rows appear; idempotent on re-run per the seed script's own docstring.

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/rbac/public.py backend/app/modules/rbac/constants.py
git commit -m "feat(rbac): add has_permission facade method and cloudflare_account catalog entries"
```

---

## Task 8: `dependencies.py` — `require_account_access` (Layer 2)

**Files:**
- Create: `backend/app/modules/cloudflare/dependencies.py`
- Test: `backend/tests/cloudflare/test_dependencies.py`

**Interfaces:**
- Consumes: `AbstractCloudflareUnitOfWork` (Task 6), `CloudflareAccountRules.satisfies_level` (Task 4), `AuthApi`/`get_auth_api` from `app.modules.auth.public`, `RbacApi`/`get_rbac_api` from `app.modules.rbac.public` (Task 7's new `has_permission`), `UserRead` from `app.modules.users.public`.
- Produces: `require_account_access(min_level: AccessLevel)` — a dependency factory returning a `check(account_id: UUID, ...) -> AccountAccessGrant` closure, mirroring `rbac/public.py`'s `require_permission` shape but resolving the path param `account_id` and returning the grant (imported from Task 3's `schemas.py`, NOT defined here — see that class's docstring for why) instead of raising-or-passing a bare `UserRead`. Every router task (10 endpoints) and the `UpdateCloudflareAccount` service (Task 10) depend on this exact `AccountAccessGrant` shape.
- Also produces: `get_uow`, `get_cloudflare_client` (plain `CloudflareClient()` provider) — used by every service-provider function in Task 17's `dependencies.py` extension.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for app.modules.cloudflare.dependencies.require_account_access —
Fake-based, no database. Exercises the closure returned by the factory directly."""

from uuid import uuid4

import pytest

from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.dependencies import require_account_access
from app.modules.cloudflare.exceptions import InsufficientAccountAccess
from app.modules.cloudflare.repository import CloudflareAccountManagerRow
from app.modules.users.public import UserRead

pytestmark = pytest.mark.anyio

# UserRead.model_construct bypasses field validation/required-field checks —
# these tests only ever read .id off the fake user, and model_construct is
# the standard pydantic way to build a test fixture without knowing every
# field UserRead happens to require.
_FAKE_USER = UserRead.model_construct(id=uuid4())


class FakeAuthApi:
    def __init__(self, user) -> None:
        self._user = user

    def current_user(self):
        return self._user


class FakeRbacApi:
    def __init__(self, *, manage_all: bool) -> None:
        self._manage_all = manage_all

    async def has_permission(self, user_id, resource, action) -> bool:
        assert (resource, action) == ("cloudflare_account", "manage_all")
        return self._manage_all


class FakeAccountManagers:
    def __init__(self, row: CloudflareAccountManagerRow | None) -> None:
        self._row = row

    async def get_for_user(self, account_id, user_id):
        return self._row


class FakeUow:
    def __init__(self, manager_row: CloudflareAccountManagerRow | None) -> None:
        self.account_managers = FakeAccountManagers(manager_row)


def _make_uow(manager_row: CloudflareAccountManagerRow | None) -> FakeUow:
    return FakeUow(manager_row)


async def test_manage_all_bypasses_with_held_level_none() -> None:
    check = require_account_access(AccessLevel.OWNER)
    grant = await check(
        account_id=uuid4(),
        auth_api=FakeAuthApi(_FAKE_USER),
        rbac_api=FakeRbacApi(manage_all=True),
        uow=_make_uow(None),
    )
    assert grant.held_level is None


async def test_sufficient_manager_row_passes() -> None:
    account_id = uuid4()
    row = CloudflareAccountManagerRow(
        cloudflare_account_id=account_id,
        user_id=_FAKE_USER.id,
        access_level=AccessLevel.OWNER,
        created_at=None,
    )
    check = require_account_access(AccessLevel.EDITOR)
    grant = await check(
        account_id=account_id,
        auth_api=FakeAuthApi(_FAKE_USER),
        rbac_api=FakeRbacApi(manage_all=False),
        uow=_make_uow(row),
    )
    assert grant.held_level is AccessLevel.OWNER


async def test_insufficient_manager_row_raises() -> None:
    account_id = uuid4()
    row = CloudflareAccountManagerRow(
        cloudflare_account_id=account_id,
        user_id=_FAKE_USER.id,
        access_level=AccessLevel.VIEWER,
        created_at=None,
    )
    check = require_account_access(AccessLevel.OWNER)
    with pytest.raises(InsufficientAccountAccess):
        await check(
            account_id=account_id,
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False),
            uow=_make_uow(row),
        )


async def test_no_manager_row_and_no_manage_all_raises() -> None:
    check = require_account_access(AccessLevel.VIEWER)
    with pytest.raises(InsufficientAccountAccess):
        await check(
            account_id=uuid4(),
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False),
            uow=_make_uow(None),
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_dependencies.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.cloudflare.dependencies'`

- [ ] **Step 3: Write `dependencies.py`**

```python
"""FastAPI dependency providers for the cloudflare module. Every provider
depends on an Abstract* contract."""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
from app.modules.auth.public import AuthApi, get_auth_api
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.exceptions import InsufficientAccountAccess
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.schemas import AccountAccessGrant
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork, CloudflareUnitOfWork
from app.modules.rbac.public import RbacApi, get_rbac_api


async def get_uow(
    session: AsyncSession = Depends(get_session), cache: CacheClient = Depends(get_cache)
) -> CloudflareUnitOfWork:
    """Provide a request scoped unit of work. The one place the concrete class is named."""
    return CloudflareUnitOfWork(session, cache)


async def get_cloudflare_client() -> CloudflareClient:
    """Provide the Cloudflare API client. No transport override in production."""
    return CloudflareClient()


def require_account_access(min_level: AccessLevel):
    """Return a dependency that 403s unless the current user's per-account
    access_level (cloudflare_account_managers) meets min_level, OR they hold
    the cloudflare_account:manage_all Layer-1 permission. Returns the
    resolved AccountAccessGrant rather than a bare UserRead — callers that
    need a stricter, request-body-dependent check (UpdateCloudflareAccount's
    OWNER-for-token-rotation rule) re-validate the grant themselves instead
    of this being expressible as a second static Depends factory."""

    async def check(
        account_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    ) -> AccountAccessGrant:
        user = auth_api.current_user()
        if await rbac_api.has_permission(user.id, "cloudflare_account", "manage_all"):
            return AccountAccessGrant(user=user, held_level=None)

        manager_row = await uow.account_managers.get_for_user(account_id, user.id)
        # IMPORTANT: do not funnel "no row" through satisfies_level(None, ...) —
        # None there means "manage_all bypass, always sufficient" (see rules.py),
        # which is a DIFFERENT meaning than "no relationship to this account at
        # all". Guard the no-row case explicitly so the two never collide.
        if manager_row is None or not CloudflareAccountRules.satisfies_level(
            manager_row.access_level, min_level
        ):
            raise InsufficientAccountAccess()
        return AccountAccessGrant(user=user, held_level=manager_row.access_level)

    return check
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_dependencies.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/dependencies.py backend/tests/cloudflare/test_dependencies.py
git commit -m "feat(cloudflare): add require_account_access Layer-2 dependency"
```

---

## Task 9: Test Fakes + `CreateCloudflareAccount`

This task establishes `backend/tests/cloudflare/test_services.py`, shared by every remaining service task (Tasks 10-16 each append one more `TestXxx` class plus, where needed, one more Fake — mirrors how `tests/projects/test_services.py` bundles all 6 of Phase 1's services in one file).

**Files:**
- Create: `backend/app/modules/cloudflare/services/__init__.py` (empty)
- Create: `backend/app/modules/cloudflare/services/create_account.py`
- Create: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Consumes: `AbstractCloudflareUnitOfWork`/`AbstractCloudflareAccountRepository`/`AbstractCloudflareAccountManagerRepository` (Task 6), `CloudflareClient` (Task 5), `AuditApi`/`AuditActor`/`AuditEventType`/`AuditSource`/`AuditSeverity` (existing `app.modules.audit.public`/`.constants`), `FernetCodec` (`app.core.crypto`), `CloudflareAccountAuditActions` (Task 2), `AccessLevel` (Task 2).
- Produces: `CreateCloudflareAccount(uow, client, audit_api).execute(label, cf_account_id, api_token, *, actor_id, actor_email) -> CloudflareAccountRead`. Test fakes `FakeCloudflareAccountRepository`, `FakeCloudflareAccountManagerRepository`, `FakeCloudflareUnitOfWork`, `FakeCloudflareClient` (configurable to raise `InvalidCloudflareToken`/`CloudflareApiUnavailable` or succeed), `FakeAuditApi` (identical shape to `tests/projects/test_services.py`'s), module-level `ACTOR_ID`/`ACTOR_EMAIL` — every later service test in this file reuses all of these.

- [ ] **Step 1: Write the failing tests (Fakes + `TestCreateCloudflareAccount`)**

```python
"""Unit tests for app.modules.cloudflare.services — Fake-based, no database,
no real Cloudflare API calls."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareApiUnavailable as CfUnavailable
from app.modules.cloudflare.exceptions import InvalidCloudflareToken
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    CloudflareAccountManagerRow,
)
from app.modules.cloudflare.schemas import CloudflareAccountRead
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class FakeCloudflareAccountRepository(AbstractCloudflareAccountRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, CloudflareAccountRead] = {}
        self._ciphertexts: dict[UUID, str] = {}

    async def get_by_id(self, entity_id: UUID) -> CloudflareAccountRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_ids(self, account_ids: list[UUID]) -> list[CloudflareAccountRead]:
        return [self._rows[i] for i in account_ids if i in self._rows]

    async def create(
        self, *, label: str, cf_account_id: str, api_token: str, created_by: UUID | None
    ) -> CloudflareAccountRead:
        account = CloudflareAccountRead(
            id=uuid4(),
            label=label,
            cf_account_id=cf_account_id,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[account.id] = account
        self._ciphertexts[account.id] = api_token
        return account

    async def update(
        self, account_id: UUID, *, label: str | None, api_token: str | None
    ) -> CloudflareAccountRead:
        existing = self._rows[account_id]
        updated = existing.model_copy(update={"label": label if label is not None else existing.label})
        self._rows[account_id] = updated
        if api_token is not None:
            self._ciphertexts[account_id] = api_token
        return updated

    async def delete(self, account_id: UUID) -> None:
        self._rows.pop(account_id, None)
        self._ciphertexts.pop(account_id, None)

    async def get_token_ciphertext(self, account_id: UUID) -> str | None:
        return self._ciphertexts.get(account_id)


class FakeCloudflareAccountManagerRepository(AbstractCloudflareAccountManagerRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID], CloudflareAccountManagerRow] = {}

    async def get_by_id(self, entity_id: tuple) -> CloudflareAccountManagerRow | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareAccountManagerRow], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def get_for_user(self, account_id: UUID, user_id: UUID) -> CloudflareAccountManagerRow | None:
        return self._rows.get((account_id, user_id))

    async def list_for_account(self, account_id: UUID) -> list[CloudflareAccountManagerRow]:
        return [r for (aid, _), r in self._rows.items() if aid == account_id]

    async def list_for_user(self, user_id: UUID) -> list[CloudflareAccountManagerRow]:
        return [r for (_, uid), r in self._rows.items() if uid == user_id]

    async def count_owners(self, account_id: UUID) -> int:
        return sum(
            1
            for (aid, _), r in self._rows.items()
            if aid == account_id and r.access_level == AccessLevel.OWNER
        )

    async def upsert(
        self, account_id: UUID, user_id: UUID, access_level: AccessLevel
    ) -> CloudflareAccountManagerRow:
        row = CloudflareAccountManagerRow(
            cloudflare_account_id=account_id,
            user_id=user_id,
            access_level=access_level,
            created_at=datetime.now(UTC),
        )
        self._rows[(account_id, user_id)] = row
        return row

    async def remove(self, account_id: UUID, user_id: UUID) -> None:
        self._rows.pop((account_id, user_id), None)


class FakeCloudflareUnitOfWork(AbstractCloudflareUnitOfWork):
    """In-memory unit of work. commit/rollback are no-ops that just count calls."""

    def __init__(self) -> None:
        self.accounts = FakeCloudflareAccountRepository()
        self.account_managers = FakeCloudflareAccountManagerRepository()
        self.commits = 0
        self.rollbacks = 0
        self.stale: list[tuple[str, UUID]] = []

    def mark_stale(self, entity: str, entity_id: UUID) -> None:
        self.stale.append((entity, entity_id))

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeCloudflareClient:
    """Duck-typed stand-in for CloudflareClient — configurable to raise or succeed."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[tuple[str, str]] = []

    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        self.calls.append((cf_account_id, api_token))
        if self._raises is not None:
            raise self._raises


class FakeAuditApi:
    """Duck-typed stand-in for app.modules.audit.public.AuditApi — records every
    call instead of writing to Mongo, so tests can assert an event was logged."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def log_event(self, **kwargs) -> None:
        self.events.append(kwargs)

    async def list_logs(self, **kwargs) -> tuple[list, int]:
        return [], 0


ACTOR_ID = uuid4()
ACTOR_EMAIL = "actor@example.com"


class TestCreateCloudflareAccount:
    async def test_creates_account_and_assigns_creator_as_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient()
        audit_api = FakeAuditApi()

        account = await CreateCloudflareAccount(uow, client, audit_api).execute(
            "CF - Customer A", "cf-acc-1", "real-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert account.label == "CF - Customer A"
        manager = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert manager is not None
        assert manager.access_level is AccessLevel.OWNER
        assert client.calls == [("cf-acc-1", "real-token")]
        assert uow.commits == 1
        assert audit_api.events[0]["action"] == CloudflareAccountAuditActions.ACCOUNT_CREATED

    async def test_stores_token_as_ciphertext_not_plaintext(self, monkeypatch) -> None:
        from app.modules.cloudflare.config import cloudflare_settings

        monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s=")
        uow = FakeCloudflareUnitOfWork()

        account = await CreateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            "CF - Customer A", "cf-acc-1", "super-secret-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored != "super-secret-token"

    async def test_rejects_bad_token_before_persisting_anything(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient(raises=InvalidCloudflareToken())

        with pytest.raises(InvalidCloudflareToken):
            await CreateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                "CF - Bad", "cf-acc-2", "bad-token", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0
        items, total = await uow.accounts.list_page(50, 0)
        assert total == 0

    async def test_rejects_unreachable_cloudflare_before_persisting_anything(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        client = FakeCloudflareClient(raises=CfUnavailable())

        with pytest.raises(CfUnavailable):
            await CreateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                "CF - Down", "cf-acc-3", "x", actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.cloudflare.services'`

- [ ] **Step 3: Write `services/create_account.py`**

```python
"""Create a Cloudflare account: Cloudflare must confirm the token BEFORE
anything is persisted, then the creator becomes the account's first OWNER."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.schemas import CloudflareAccountRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class CreateCloudflareAccount(AbstractUseCase):
    """Create an account, testing the token against Cloudflare's API first —
    same "call the external API before persisting" principle later DNS/Tunnel
    phases reuse. The creator becomes the account's first OWNER (mirrors
    CreateProject's auto-inserted default links: bootstrapping logic lives in
    the use case, not a template row)."""

    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, label: str, cf_account_id: str, api_token: str, *, actor_id: UUID, actor_email: str
    ) -> CloudflareAccountRead:
        await self._client.test_connection(cf_account_id=cf_account_id, api_token=api_token)

        ciphertext = FernetCodec.encrypt(api_token, key=cloudflare_settings.FERNET_KEY)
        account = await self._uow.accounts.create(
            label=label, cf_account_id=cf_account_id, api_token=ciphertext, created_by=actor_id
        )
        await self._uow.account_managers.upsert(account.id, actor_id, AccessLevel.OWNER)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.ACCOUNT_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare account '{account.label}' created",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return account
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/__init__.py backend/app/modules/cloudflare/services/create_account.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add CreateCloudflareAccount with test fakes"
```

---

## Task 10: `UpdateCloudflareAccount` (body-dependent Layer-2 re-check)

**Files:**
- Create: `backend/app/modules/cloudflare/services/update_account.py`
- Modify: `backend/tests/cloudflare/test_services.py` (append `TestUpdateCloudflareAccount`, add one import)

**Interfaces:**
- Consumes: `AccountAccessGrant` (Task 3's `schemas.py`), `CloudflareAccountRules.required_level_for_update`/`satisfies_level` (Task 4), everything Task 9 already imports.
- Produces: `UpdateCloudflareAccount(uow, client, audit_api).execute(account_id, *, label, api_token, grant, actor_email) -> CloudflareAccountRead`. This is the ONE place the structural correction from the pressure-test is implemented — Task 17's router passes the `AccountAccessGrant` it got from `require_account_access(AccessLevel.EDITOR)` (the floor) straight into this use case, which re-validates OWNER only when `api_token is not None`.

- [ ] **Step 1: Write the failing tests**

Add this import alongside the existing ones at the top of `backend/tests/cloudflare/test_services.py`:

```python
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound, InsufficientAccountAccess
from app.modules.cloudflare.schemas import AccountAccessGrant
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
```

Append to the end of the file:

```python
def _grant(held_level: AccessLevel | None) -> AccountAccessGrant:
    from app.modules.users.public import UserRead

    return AccountAccessGrant(user=UserRead.model_construct(id=ACTOR_ID), held_level=held_level)


class TestUpdateCloudflareAccount:
    async def test_editor_can_rename_label(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        updated = await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            account.id,
            label="New",
            api_token=None,
            grant=_grant(AccessLevel.EDITOR),
            actor_email=ACTOR_EMAIL,
        )

        assert updated.label == "New"
        assert uow.commits == 1

    async def test_editor_cannot_rotate_token(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(InsufficientAccountAccess):
            await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
                account.id,
                label=None,
                api_token="new-token",
                grant=_grant(AccessLevel.EDITOR),
                actor_email=ACTOR_EMAIL,
            )

        assert uow.commits == 0

    async def test_owner_can_rotate_token(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )
        client = FakeCloudflareClient()

        await UpdateCloudflareAccount(uow, client, FakeAuditApi()).execute(
            account.id,
            label=None,
            api_token="new-plaintext-token",
            grant=_grant(AccessLevel.OWNER),
            actor_email=ACTOR_EMAIL,
        )

        assert client.calls == [("cf-1", "new-plaintext-token")]
        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored != "new-plaintext-token"
        assert stored != "old-ciphertext"

    async def test_manage_all_bypass_can_rotate_token(self) -> None:
        """held_level=None (manage_all bypass) satisfies OWNER too."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )

        await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
            account.id,
            label=None,
            api_token="rotated",
            grant=_grant(None),
            actor_email=ACTOR_EMAIL,
        )

        assert uow.commits == 1

    async def test_rejects_bad_rotated_token_before_persisting(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Old", cf_account_id="cf-1", api_token="old-ciphertext", created_by=ACTOR_ID
        )
        client = FakeCloudflareClient(raises=InvalidCloudflareToken())

        with pytest.raises(InvalidCloudflareToken):
            await UpdateCloudflareAccount(uow, client, FakeAuditApi()).execute(
                account.id,
                label=None,
                api_token="bad-token",
                grant=_grant(AccessLevel.OWNER),
                actor_email=ACTOR_EMAIL,
            )

        assert uow.commits == 0
        stored = await uow.accounts.get_token_ciphertext(account.id)
        assert stored == "old-ciphertext"

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await UpdateCloudflareAccount(uow, FakeCloudflareClient(), FakeAuditApi()).execute(
                uuid4(), label="X", api_token=None, grant=_grant(AccessLevel.OWNER), actor_email=ACTOR_EMAIL
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestUpdateCloudflareAccount -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.cloudflare.services.update_account'`

- [ ] **Step 3: Write `services/update_account.py`**

```python
"""Update a Cloudflare account: rename its label and/or rotate its token."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound, InsufficientAccountAccess
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.schemas import AccountAccessGrant, CloudflareAccountRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class UpdateCloudflareAccount(AbstractUseCase):
    """Rename and/or rotate an account's token.

    Structural correction from the Phase 3 pressure-test: the router's
    require_account_access(EDITOR) dependency is only a FLOOR check — it
    cannot know at decoration time whether this particular request rotates
    the token, since min_level is bound before any request (or its body)
    exists. The body-dependent OWNER requirement is therefore re-validated
    HERE, against the AccountAccessGrant the router already resolved, rather
    than being stapled onto a second Depends factory that has no way to see
    the parsed request body.
    """

    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        account_id: UUID,
        *,
        label: str | None,
        api_token: str | None,
        grant: AccountAccessGrant,
        actor_email: str,
    ) -> CloudflareAccountRead:
        existing = await self._uow.accounts.get_by_id(account_id)
        if existing is None:
            raise CloudflareAccountNotFound()

        rotates_token = api_token is not None
        required = CloudflareAccountRules.required_level_for_update(rotates_token=rotates_token)
        if not CloudflareAccountRules.satisfies_level(grant.held_level, required):
            raise InsufficientAccountAccess()

        ciphertext = None
        if rotates_token:
            await self._client.test_connection(cf_account_id=existing.cf_account_id, api_token=api_token)
            ciphertext = FernetCodec.encrypt(api_token, key=cloudflare_settings.FERNET_KEY)

        account = await self._uow.accounts.update(account_id, label=label, api_token=ciphertext)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.ACCOUNT_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare account '{account.label}' updated",
            actor=AuditActor(user_id=grant.user.id, email=actor_email),
        )
        return account
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestUpdateCloudflareAccount -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/update_account.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add UpdateCloudflareAccount with in-service OWNER re-check"
```

---

## Task 11: `DeleteCloudflareAccount`

**Files:**
- Create: `backend/app/modules/cloudflare/services/delete_account.py`
- Modify: `backend/tests/cloudflare/test_services.py` (append `TestDeleteCloudflareAccount`)

**Interfaces:**
- Produces: `DeleteCloudflareAccount(uow, audit_api).execute(account_id, *, actor_id, actor_email) -> None`. Router gates this with `require_account_access(AccessLevel.OWNER)` directly (no body-dependent logic, unlike Task 10) — the service does not need a `grant` parameter.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/cloudflare/test_services.py`:

```python
from app.modules.cloudflare.services.delete_account import DeleteCloudflareAccount


class TestDeleteCloudflareAccount:
    async def test_deletes_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="Gone", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        await DeleteCloudflareAccount(uow, FakeAuditApi()).execute(
            account.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.accounts.get_by_id(account.id) is None
        assert uow.commits == 1

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await DeleteCloudflareAccount(uow, FakeAuditApi()).execute(
                uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert uow.commits == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestDeleteCloudflareAccount -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `services/delete_account.py`**

```python
"""Delete a Cloudflare account. Its manager rows cascade at the DB level."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class DeleteCloudflareAccount(AbstractUseCase):
    """Delete an account. Router gates this with require_account_access(OWNER)
    directly — no request-body-dependent decision, unlike UpdateCloudflareAccount."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, account_id: UUID, *, actor_id: UUID, actor_email: str) -> None:
        existing = await self._uow.accounts.get_by_id(account_id)
        if existing is None:
            raise CloudflareAccountNotFound()

        await self._uow.accounts.delete(account_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.ACCOUNT_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare account '{existing.label}' deleted",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestDeleteCloudflareAccount -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/delete_account.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add DeleteCloudflareAccount"
```

---

## Task 12: `TestCloudflareAccountConnection`

**Files:**
- Create: `backend/app/modules/cloudflare/services/test_connection.py`
- Modify: `backend/tests/cloudflare/test_services.py` (append `TestTestCloudflareAccountConnection`)

**Interfaces:**
- Produces: `TestCloudflareAccountConnection(uow, client).execute(account_id) -> None`. Decrypts the stored ciphertext and re-runs the same Cloudflare check `CreateCloudflareAccount` runs at entry time — surfaced as a manual "Test Connection" button so a user can re-verify a token hasn't since been revoked on Cloudflare's side. Router gates this with `require_account_access(AccessLevel.EDITOR)`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/cloudflare/test_services.py`:

```python
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection


class TestTestCloudflareAccountConnection:
    async def test_calls_client_with_decrypted_token(self, monkeypatch) -> None:
        from app.core.crypto import FernetCodec
        from app.modules.cloudflare.config import cloudflare_settings

        key = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="
        monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", key)
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("plain-token", key=key)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        client = FakeCloudflareClient()

        await TestCloudflareAccountConnection(uow, client).execute(account.id)

        assert client.calls == [("cf-1", "plain-token")]

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await TestCloudflareAccountConnection(uow, FakeCloudflareClient()).execute(uuid4())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestTestCloudflareAccountConnection -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `services/test_connection.py`**

```python
"""Re-verify an already-saved Cloudflare account's token is still accepted."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class TestCloudflareAccountConnection(AbstractUseCase):
    """Re-run the same connectivity check CreateCloudflareAccount runs at
    entry time, using the account's already-stored (decrypted here) token —
    surfaced as a manual "Test Connection" button so a user can re-verify a
    token hasn't since been revoked on Cloudflare's side."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID) -> None:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        await self._client.test_connection(cf_account_id=account.cf_account_id, api_token=plaintext)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestTestCloudflareAccountConnection -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/test_connection.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add TestCloudflareAccountConnection"
```

---

## Task 13: `RevealCloudflareAccountToken`

**Files:**
- Create: `backend/app/modules/cloudflare/services/reveal_token.py`
- Modify: `backend/tests/cloudflare/test_services.py` (append `TestRevealCloudflareAccountToken`)

**Interfaces:**
- Produces: `RevealCloudflareAccountToken(uow, audit_api).execute(account_id, *, actor_id, actor_email) -> str` (the decrypted plaintext token). Router gates this with `require_account_access(AccessLevel.OWNER)`. The audit entry's `message`/no `payload` field NEVER contains the token value — only `{account_id}`-adjacent context and the actor, per the Global Constraints.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/cloudflare/test_services.py`:

```python
from app.modules.cloudflare.services.reveal_token import RevealCloudflareAccountToken


class TestRevealCloudflareAccountToken:
    async def test_returns_decrypted_token_and_audits_without_leaking_it(self, monkeypatch) -> None:
        from app.core.crypto import FernetCodec
        from app.modules.cloudflare.config import cloudflare_settings

        key = "kL8Zx3vQ9mN2pR7wT4yU6bC1dF5gH0jK3lM6nO9pQ2s="
        monkeypatch.setattr(cloudflare_settings, "FERNET_KEY", key)
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("super-secret", key=key)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        audit_api = FakeAuditApi()

        revealed = await RevealCloudflareAccountToken(uow, audit_api).execute(
            account.id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert revealed == "super-secret"
        event = audit_api.events[0]
        assert event["action"] == CloudflareAccountAuditActions.TOKEN_REVEALED
        assert "super-secret" not in str(event)

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await RevealCloudflareAccountToken(uow, FakeAuditApi()).execute(
                uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestRevealCloudflareAccountToken -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `services/reveal_token.py`**

```python
"""Reveal a Cloudflare account's plaintext token, on demand only."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class RevealCloudflareAccountToken(AbstractUseCase):
    """Decrypt and return an account's plaintext token. Router gates this
    with require_account_access(OWNER). The audit entry logs the account and
    actor only — NEVER the decrypted token value, since Mongo's free-form
    log payload has none of Postgres's column-level discipline."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, account_id: UUID, *, actor_id: UUID, actor_email: str) -> str:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.TOKEN_REVEALED,
            severity=AuditSeverity.HIGH,
            message=f"Cloudflare account '{account.label}' token revealed",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
        return plaintext
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestRevealCloudflareAccountToken -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/reveal_token.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add RevealCloudflareAccountToken"
```

---

## Task 14: `ListCloudflareAccountManagers` (cross-module enrichment via `UsersApi`)

**Files:**
- Create: `backend/app/modules/cloudflare/services/list_account_managers.py`
- Modify: `backend/tests/cloudflare/test_services.py` (append `FakeUsersApi` + `TestListCloudflareAccountManagers`)

**Interfaces:**
- Consumes: `UsersApi`/`UserRead` from `app.modules.users.public` (existing facade — `get_user_by_id(user_id) -> UserRead | None`).
- Produces: `ListCloudflareAccountManagers(uow, users_api).execute(account_id) -> list[CloudflareAccountManagerRead]`. Router gates this with `require_account_access(AccessLevel.VIEWER)`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/cloudflare/test_services.py`:

```python
from app.modules.cloudflare.schemas import CloudflareAccountManagerRead
from app.modules.cloudflare.services.list_account_managers import ListCloudflareAccountManagers


class FakeUsersApi:
    """Duck-typed stand-in for app.modules.users.public.UsersApi."""

    def __init__(self, users: dict[UUID, object]) -> None:
        self._users = users

    async def get_user_by_id(self, user_id: UUID):
        return self._users.get(user_id)


class TestListCloudflareAccountManagers:
    async def test_lists_managers_enriched_with_user_info(self) -> None:
        from app.modules.users.public import UserRead

        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        user = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL, name="Actor")
        users_api = FakeUsersApi({ACTOR_ID: user})

        managers = await ListCloudflareAccountManagers(uow, users_api).execute(account.id)

        assert len(managers) == 1
        assert managers[0].email == ACTOR_EMAIL
        assert managers[0].access_level is AccessLevel.OWNER

    async def test_skips_a_manager_row_whose_user_was_deleted(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        users_api = FakeUsersApi({})  # ACTOR_ID resolves to None

        managers = await ListCloudflareAccountManagers(uow, users_api).execute(account.id)

        assert managers == []

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await ListCloudflareAccountManagers(uow, FakeUsersApi({})).execute(uuid4())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestListCloudflareAccountManagers -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `services/list_account_managers.py`**

```python
"""List an account's managers, enriched with each user's email/name."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.schemas import CloudflareAccountManagerRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UsersApi


class ListCloudflareAccountManagers(AbstractUseCase):
    """Return every manager row for an account, enriched with the target
    user's email/name — the repository only knows user_id; resolving a
    human-readable identity is cross-module composition, which belongs in a
    use case, never the router or the repository."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, users_api: UsersApi) -> None:
        self._uow = uow
        self._users_api = users_api

    @use_case
    async def execute(self, account_id: UUID) -> list[CloudflareAccountManagerRead]:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()

        rows = await self._uow.account_managers.list_for_account(account_id)
        result: list[CloudflareAccountManagerRead] = []
        for row in rows:
            user = await self._users_api.get_user_by_id(row.user_id)
            if user is None:
                continue
            result.append(
                CloudflareAccountManagerRead(
                    user_id=row.user_id,
                    email=user.email,
                    name=user.name,
                    access_level=row.access_level,
                    created_at=row.created_at,
                )
            )
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestListCloudflareAccountManagers -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/list_account_managers.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add ListCloudflareAccountManagers"
```

---

## Task 15: `AssignCloudflareAccountManager`

**Files:**
- Create: `backend/app/modules/cloudflare/services/assign_manager.py`
- Modify: `backend/tests/cloudflare/test_services.py` (append `TestAssignCloudflareAccountManager`)

**Interfaces:**
- Produces: `AssignCloudflareAccountManager(uow, audit_api).execute(account_id, target_user_id, access_level, *, actor_id, actor_email) -> None`. Router gates this with `require_account_access(AccessLevel.OWNER)`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/cloudflare/test_services.py`:

```python
from app.modules.cloudflare.services.assign_manager import AssignCloudflareAccountManager


class TestAssignCloudflareAccountManager:
    async def test_assigns_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()

        await AssignCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, AccessLevel.VIEWER, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, target_id)
        assert row is not None
        assert row.access_level is AccessLevel.VIEWER
        assert uow.commits == 1

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await AssignCloudflareAccountManager(uow, FakeAuditApi()).execute(
                uuid4(), uuid4(), AccessLevel.VIEWER, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestAssignCloudflareAccountManager -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `services/assign_manager.py`**

```python
"""Grant a user a specific access_level on a Cloudflare account."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class AssignCloudflareAccountManager(AbstractUseCase):
    """Grant (or re-grant) a user a specific access_level on an account.
    Router gates this with require_account_access(OWNER) — only an existing
    OWNER (or a manage_all holder) can hand out access to someone else."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        account_id: UUID,
        target_user_id: UUID,
        access_level: AccessLevel,
        *,
        actor_id: UUID,
        actor_email: str,
    ) -> None:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()

        await self._uow.account_managers.upsert(account_id, target_user_id, access_level)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.MANAGER_ASSIGNED,
            severity=AuditSeverity.INFO,
            message=f"User {target_user_id} assigned {access_level.value} on '{account.label}'",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestAssignCloudflareAccountManager -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/assign_manager.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add AssignCloudflareAccountManager"
```

---

## Task 16: `UpdateCloudflareAccountManager` + `RemoveCloudflareAccountManager` (shared last-owner guard)

Bundled as one task: both services share the exact same `blocks_last_owner_removal` guard (a downgrade has the same effect as a delete — Global Constraints), so their tests are best reviewed together.

**Files:**
- Create: `backend/app/modules/cloudflare/services/update_manager.py`
- Create: `backend/app/modules/cloudflare/services/remove_manager.py`
- Modify: `backend/tests/cloudflare/test_services.py` (append `TestUpdateCloudflareAccountManager` + `TestRemoveCloudflareAccountManager`)

**Interfaces:**
- Produces: `UpdateCloudflareAccountManager(uow, audit_api).execute(account_id, target_user_id, new_access_level, *, actor_id, actor_email) -> None`; `RemoveCloudflareAccountManager(uow, audit_api).execute(account_id, target_user_id, *, actor_id, actor_email) -> None`. Both gated by the router with `require_account_access(AccessLevel.OWNER)`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py`:

```python
from app.modules.cloudflare.exceptions import CloudflareAccountManagerNotFound, LastOwnerRemovalBlocked
from app.modules.cloudflare.services.remove_manager import RemoveCloudflareAccountManager
from app.modules.cloudflare.services.update_manager import UpdateCloudflareAccountManager


class TestUpdateCloudflareAccountManager:
    async def test_changes_access_level(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.VIEWER)

        await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, target_id)
        assert row.access_level is AccessLevel.EDITOR

    async def test_blocks_downgrading_the_last_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)

        with pytest.raises(LastOwnerRemovalBlocked):
            await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, ACTOR_ID, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        row = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert row.access_level is AccessLevel.OWNER

    async def test_allows_downgrading_one_of_two_owners(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        second_owner = uuid4()
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        await uow.account_managers.upsert(account.id, second_owner, AccessLevel.OWNER)

        await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, ACTOR_ID, AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        row = await uow.account_managers.get_for_user(account.id, ACTOR_ID)
        assert row.access_level is AccessLevel.EDITOR

    async def test_rejects_unknown_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(CloudflareAccountManagerNotFound):
            await UpdateCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, uuid4(), AccessLevel.EDITOR, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )


class TestRemoveCloudflareAccountManager:
    async def test_removes_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.VIEWER)

        await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.account_managers.get_for_user(account.id, target_id) is None

    async def test_blocks_removing_the_last_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)

        with pytest.raises(LastOwnerRemovalBlocked):
            await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, ACTOR_ID, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )

        assert await uow.account_managers.get_for_user(account.id, ACTOR_ID) is not None

    async def test_allows_removing_a_non_owner(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        target_id = uuid4()
        await uow.account_managers.upsert(account.id, target_id, AccessLevel.EDITOR)

        await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
            account.id, target_id, actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
        )

        assert await uow.account_managers.get_for_user(account.id, target_id) is None

    async def test_rejects_unknown_manager(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )

        with pytest.raises(CloudflareAccountManagerNotFound):
            await RemoveCloudflareAccountManager(uow, FakeAuditApi()).execute(
                account.id, uuid4(), actor_id=ACTOR_ID, actor_email=ACTOR_EMAIL
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k "UpdateCloudflareAccountManager or RemoveCloudflareAccountManager" -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `services/update_manager.py`**

```python
"""Change a manager's access_level on a Cloudflare account."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountManagerNotFound, LastOwnerRemovalBlocked
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class UpdateCloudflareAccountManager(AbstractUseCase):
    """Change a manager's access_level. Router gates this with
    require_account_access(OWNER). Downgrading the last OWNER has the same
    effect as removing them, so it is blocked by the identical guard
    RemoveCloudflareAccountManager uses — see CloudflareAccountRules.
    blocks_last_owner_removal's docstring for why there is no manage_all
    exemption."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        account_id: UUID,
        target_user_id: UUID,
        new_access_level: AccessLevel,
        *,
        actor_id: UUID,
        actor_email: str,
    ) -> None:
        existing = await self._uow.account_managers.get_for_user(account_id, target_user_id)
        if existing is None:
            raise CloudflareAccountManagerNotFound()

        if existing.access_level == AccessLevel.OWNER and new_access_level != AccessLevel.OWNER:
            owner_count = await self._uow.account_managers.count_owners(account_id)
            if CloudflareAccountRules.blocks_last_owner_removal(existing.access_level, owner_count):
                raise LastOwnerRemovalBlocked()

        await self._uow.account_managers.upsert(account_id, target_user_id, new_access_level)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.MANAGER_UPDATED,
            severity=AuditSeverity.INFO,
            message=(
                f"User {target_user_id}'s access on account {account_id} "
                f"changed to {new_access_level.value}"
            ),
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
```

- [ ] **Step 4: Write `services/remove_manager.py`**

```python
"""Remove a user's access to a Cloudflare account."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountManagerNotFound, LastOwnerRemovalBlocked
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class RemoveCloudflareAccountManager(AbstractUseCase):
    """Remove a user's manager row entirely. Router gates this with
    require_account_access(OWNER)."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, account_id: UUID, target_user_id: UUID, *, actor_id: UUID, actor_email: str
    ) -> None:
        existing = await self._uow.account_managers.get_for_user(account_id, target_user_id)
        if existing is None:
            raise CloudflareAccountManagerNotFound()

        if existing.access_level == AccessLevel.OWNER:
            owner_count = await self._uow.account_managers.count_owners(account_id)
            if CloudflareAccountRules.blocks_last_owner_removal(existing.access_level, owner_count):
                raise LastOwnerRemovalBlocked()

        await self._uow.account_managers.remove(account_id, target_user_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareAccountAuditActions.MANAGER_REMOVED,
            severity=AuditSeverity.INFO,
            message=f"User {target_user_id}'s access on account {account_id} removed",
            actor=AuditActor(user_id=actor_id, email=actor_email),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -v`
Expected: PASS (all tests in the file — this is the last service task, a full run confirms every service composes correctly together)

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/cloudflare/services/update_manager.py backend/app/modules/cloudflare/services/remove_manager.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add UpdateCloudflareAccountManager and RemoveCloudflareAccountManager with last-owner guard"
```

---

## Task 17: `ListVisibleCloudflareAccounts` (filtered `GET /cloudflare-accounts`)

**Files:**
- Create: `backend/app/modules/cloudflare/services/list_visible_accounts.py`
- Modify: `backend/tests/cloudflare/test_services.py` (append `FakeRbacApi` + `TestListVisibleCloudflareAccounts`)

**Interfaces:**
- Consumes: `RbacApi` from `app.modules.rbac.public` (Task 7's `has_permission`).
- Produces: `ListVisibleCloudflareAccounts(uow, rbac_api).execute(user_id) -> list[CloudflareAccountRead]`. Backs `GET /cloudflare-accounts` — per the master-plan demo wording ("a user with neither `manage_all` nor a managers row sees nothing"), this returns an **empty list**, never a 403 (Layer 1's `view` permission already gated reaching this use case at all).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/cloudflare/test_services.py`:

```python
from app.modules.cloudflare.services.list_visible_accounts import ListVisibleCloudflareAccounts


class FakeRbacApi:
    """Duck-typed stand-in for app.modules.rbac.public.RbacApi — only the one
    method this module's services actually call."""

    def __init__(self, *, manage_all: bool) -> None:
        self._manage_all = manage_all

    async def has_permission(self, user_id, resource, action) -> bool:
        return self._manage_all


class TestListVisibleCloudflareAccounts:
    async def test_manage_all_sees_every_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        await uow.accounts.create(label="A", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID)
        await uow.accounts.create(label="B", cf_account_id="cf-2", api_token="x", created_by=ACTOR_ID)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=True)).execute(
            uuid4()
        )

        assert {a.label for a in accounts} == {"A", "B"}

    async def test_regular_user_sees_only_managed_accounts(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        visible = await uow.accounts.create(
            label="Visible", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID
        )
        await uow.accounts.create(label="Hidden", cf_account_id="cf-2", api_token="x", created_by=ACTOR_ID)
        await uow.account_managers.upsert(visible.id, ACTOR_ID, AccessLevel.VIEWER)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=False)).execute(
            ACTOR_ID
        )

        assert [a.label for a in accounts] == ["Visible"]

    async def test_user_with_no_relationship_sees_nothing(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        await uow.accounts.create(label="A", cf_account_id="cf-1", api_token="x", created_by=ACTOR_ID)

        accounts = await ListVisibleCloudflareAccounts(uow, FakeRbacApi(manage_all=False)).execute(
            uuid4()
        )

        assert accounts == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestListVisibleCloudflareAccounts -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `services/list_visible_accounts.py`**

```python
"""List Cloudflare accounts visible to the current user."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.schemas import CloudflareAccountRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.rbac.public import RbacApi


class ListVisibleCloudflareAccounts(AbstractUseCase):
    """Return every account the current user can see: all of them if they
    hold cloudflare_account:manage_all, otherwise only the accounts where
    they have a cloudflare_account_managers row (any level). A user with
    neither gets an empty list, not a 403 — Layer 1's `view` permission
    already gated reaching this use case at all; this narrows WHICH accounts,
    exactly like every other Layer-2 check in this module."""

    def __init__(self, uow: AbstractCloudflareUnitOfWork, rbac_api: RbacApi) -> None:
        self._uow = uow
        self._rbac_api = rbac_api

    @use_case
    async def execute(self, user_id: UUID) -> list[CloudflareAccountRead]:
        if await self._rbac_api.has_permission(user_id, "cloudflare_account", "manage_all"):
            # Phase 3 scope: a single generously-sized page. Real pagination
            # for the manage_all view is deferred — the account count stays
            # small through at least Phase 5 (one row per Cloudflare account,
            # not per project/environment).
            items, _total = await self._uow.accounts.list_page(limit=1000, offset=0)
            return items

        manager_rows = await self._uow.account_managers.list_for_user(user_id)
        account_ids = [row.cloudflare_account_id for row in manager_rows]
        return await self._uow.accounts.list_for_ids(account_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -v`
Expected: PASS (all tests in the file, 10 service classes total)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/list_visible_accounts.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add ListVisibleCloudflareAccounts"
```

---

## Task 18: `dependencies.py` provider functions + `router.py` (10 endpoints)

**Files:**
- Modify: `backend/app/modules/cloudflare/dependencies.py` (append provider functions — Task 8 already wrote `get_uow`, `get_cloudflare_client`, `require_account_access`)
- Create: `backend/app/modules/cloudflare/router.py`

**Interfaces:**
- Consumes: every service from Tasks 9-17, `require_permission` from `rbac.public`, `get_audit_api`/`AuditApi` from `audit.public`, `get_users_api`/`UsersApi` from `users.public`, `get_rbac_api`/`RbacApi` from `rbac.public`.
- Produces: 10 registered routes under `/cloudflare-accounts`, exactly as specified in the plan's Architecture Impact table. `router = APIRouter(tags=["cloudflare"])` — consumed by Task 19's `main.py` registration.

- [ ] **Step 1: Append provider functions to `dependencies.py`**

Add these imports to the top of `backend/app/modules/cloudflare/dependencies.py` (alongside the ones Task 8 wrote):

```python
from app.modules.audit.public import AuditApi, get_audit_api
from app.modules.cloudflare.services.assign_manager import AssignCloudflareAccountManager
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
from app.modules.cloudflare.services.delete_account import DeleteCloudflareAccount
from app.modules.cloudflare.services.list_account_managers import ListCloudflareAccountManagers
from app.modules.cloudflare.services.list_visible_accounts import ListVisibleCloudflareAccounts
from app.modules.cloudflare.services.remove_manager import RemoveCloudflareAccountManager
from app.modules.cloudflare.services.reveal_token import RevealCloudflareAccountToken
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
from app.modules.cloudflare.services.update_manager import UpdateCloudflareAccountManager
from app.modules.users.public import UsersApi, get_users_api
```

Append these functions at the end of the file:

```python
async def get_create_account(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateCloudflareAccount:
    """Provide the create-account use case."""
    return CreateCloudflareAccount(uow, client, audit_api)


async def get_update_account(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateCloudflareAccount:
    """Provide the update-account use case."""
    return UpdateCloudflareAccount(uow, client, audit_api)


async def get_delete_account(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> DeleteCloudflareAccount:
    """Provide the delete-account use case."""
    return DeleteCloudflareAccount(uow, audit_api)


async def get_test_connection(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
) -> TestCloudflareAccountConnection:
    """Provide the test-connection use case."""
    return TestCloudflareAccountConnection(uow, client)


async def get_reveal_token(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> RevealCloudflareAccountToken:
    """Provide the reveal-token use case."""
    return RevealCloudflareAccountToken(uow, audit_api)


async def get_list_visible_accounts(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), rbac_api: RbacApi = Depends(get_rbac_api)
) -> ListVisibleCloudflareAccounts:
    """Provide the list-visible-accounts use case."""
    return ListVisibleCloudflareAccounts(uow, rbac_api)


async def get_list_account_managers(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), users_api: UsersApi = Depends(get_users_api)
) -> ListCloudflareAccountManagers:
    """Provide the list-account-managers use case."""
    return ListCloudflareAccountManagers(uow, users_api)


async def get_assign_manager(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> AssignCloudflareAccountManager:
    """Provide the assign-manager use case."""
    return AssignCloudflareAccountManager(uow, audit_api)


async def get_update_manager(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> UpdateCloudflareAccountManager:
    """Provide the update-manager use case."""
    return UpdateCloudflareAccountManager(uow, audit_api)


async def get_remove_manager(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> RemoveCloudflareAccountManager:
    """Provide the remove-manager use case."""
    return RemoveCloudflareAccountManager(uow, audit_api)
```

- [ ] **Step 2: Verify `dependencies.py` still imports cleanly**

Run: `cd backend && uv run python -c "from app.modules.cloudflare import dependencies; print('ok')"`
Expected: `ok` (this will surface any circular-import mistake immediately — if it fails with an import cycle, re-check that no service module imports anything from `dependencies.py`)

- [ ] **Step 3: Write `router.py`**

```python
"""HTTP entry points of the cloudflare module. Router thinness (rule #10):
every function below only translates HTTP -> use-case call and wraps the
result in ApiResponse — no formatting/business logic lives here.

Every Layer-2-gated route below ALSO declares its matching Layer-1
require_permission (view for reads, manage for writes) — Layer 2 only
narrows Layer 1, it never grants capability on its own.

PATCH /cloudflare-accounts/{account_id} is the one route whose true Layer-2
requirement is body-dependent (OWNER only when rotating the token). That
decision is made inside UpdateCloudflareAccount's use case, not here —
require_account_access(EDITOR) below is only the floor a static Depends
factory can express; see that use case's own docstring.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.models import ApiResponse
from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.dependencies import (
    get_assign_manager,
    get_create_account,
    get_delete_account,
    get_list_account_managers,
    get_list_visible_accounts,
    get_remove_manager,
    get_reveal_token,
    get_test_connection,
    get_update_account,
    get_update_manager,
    get_uow,
    require_account_access,
)
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.schemas import (
    AccountAccessGrant,
    CloudflareAccountCreate,
    CloudflareAccountManagerAssign,
    CloudflareAccountManagerRead,
    CloudflareAccountManagerUpdate,
    CloudflareAccountRead,
    CloudflareAccountUpdate,
    TokenRevealResponse,
)
from app.modules.cloudflare.services.assign_manager import AssignCloudflareAccountManager
from app.modules.cloudflare.services.create_account import CreateCloudflareAccount
from app.modules.cloudflare.services.delete_account import DeleteCloudflareAccount
from app.modules.cloudflare.services.list_account_managers import ListCloudflareAccountManagers
from app.modules.cloudflare.services.list_visible_accounts import ListVisibleCloudflareAccounts
from app.modules.cloudflare.services.remove_manager import RemoveCloudflareAccountManager
from app.modules.cloudflare.services.reveal_token import RevealCloudflareAccountToken
from app.modules.cloudflare.services.test_connection import TestCloudflareAccountConnection
from app.modules.cloudflare.services.update_account import UpdateCloudflareAccount
from app.modules.cloudflare.services.update_manager import UpdateCloudflareAccountManager
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.rbac.public import require_permission
from app.modules.users.public import UserRead

router = APIRouter(tags=["cloudflare"])


@router.post("/cloudflare-accounts")
async def create_cloudflare_account(
    body: CloudflareAccountCreate,
    use_case: CreateCloudflareAccount = Depends(get_create_account),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
) -> ApiResponse[CloudflareAccountRead]:
    """Create an account — Cloudflare must confirm the token first; the
    creator is auto-assigned OWNER. No Layer-2 check: the account doesn't
    exist yet to hold a per-account grant on."""
    account = await use_case.execute(
        body.label, body.cf_account_id, body.api_token, actor_id=user.id, actor_email=user.email
    )
    return ApiResponse[CloudflareAccountRead](success=True, data=account)


@router.get("/cloudflare-accounts")
async def list_cloudflare_accounts(
    use_case: ListVisibleCloudflareAccounts = Depends(get_list_visible_accounts),
    _user: UserRead = Depends(require_permission("cloudflare_account", "view")),
) -> ApiResponse[list[CloudflareAccountRead]]:
    """List accounts visible to the current user — filtered server-side, not
    just permission-gated (see ListVisibleCloudflareAccounts)."""
    accounts = await use_case.execute(_user.id)
    return ApiResponse[list[CloudflareAccountRead]](success=True, data=accounts)


@router.get("/cloudflare-accounts/{account_id}")
async def get_cloudflare_account(
    account_id: UUID,
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.VIEWER)),
) -> ApiResponse[CloudflareAccountRead]:
    """Return one account, 404 if it doesn't exist."""
    account = await uow.accounts.get_by_id(account_id)
    if account is None:
        raise CloudflareAccountNotFound()
    return ApiResponse[CloudflareAccountRead](success=True, data=account)


@router.patch("/cloudflare-accounts/{account_id}")
async def update_cloudflare_account(
    account_id: UUID,
    body: CloudflareAccountUpdate,
    use_case: UpdateCloudflareAccount = Depends(get_update_account),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.EDITOR)),
) -> ApiResponse[CloudflareAccountRead]:
    """Rename and/or rotate an account's token. require_account_access(EDITOR)
    above is only the floor — UpdateCloudflareAccount re-checks OWNER itself
    when the body rotates the token."""
    account = await use_case.execute(
        account_id, label=body.label, api_token=body.api_token, grant=grant, actor_email=grant.user.email
    )
    return ApiResponse[CloudflareAccountRead](success=True, data=account)


@router.delete("/cloudflare-accounts/{account_id}")
async def delete_cloudflare_account(
    account_id: UUID,
    use_case: DeleteCloudflareAccount = Depends(get_delete_account),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Delete an account. Its manager rows cascade at the DB level."""
    await use_case.execute(account_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)


@router.post("/cloudflare-accounts/{account_id}/test-connection")
async def test_cloudflare_account_connection(
    account_id: UUID,
    use_case: TestCloudflareAccountConnection = Depends(get_test_connection),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Re-verify Cloudflare still accepts the account's stored token."""
    await use_case.execute(account_id)
    return ApiResponse[None](success=True)


@router.post("/cloudflare-accounts/{account_id}/reveal-token")
async def reveal_cloudflare_account_token(
    account_id: UUID,
    use_case: RevealCloudflareAccountToken = Depends(get_reveal_token),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[TokenRevealResponse]:
    """Decrypt and return the account's plaintext token. OWNER only."""
    plaintext = await use_case.execute(account_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[TokenRevealResponse](success=True, data=TokenRevealResponse(api_token=plaintext))


@router.get("/cloudflare-accounts/{account_id}/managers")
async def list_cloudflare_account_managers(
    account_id: UUID,
    use_case: ListCloudflareAccountManagers = Depends(get_list_account_managers),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.VIEWER)),
) -> ApiResponse[list[CloudflareAccountManagerRead]]:
    """List everyone with access to this account."""
    managers = await use_case.execute(account_id)
    return ApiResponse[list[CloudflareAccountManagerRead]](success=True, data=managers)


@router.post("/cloudflare-accounts/{account_id}/managers")
async def assign_cloudflare_account_manager(
    account_id: UUID,
    body: CloudflareAccountManagerAssign,
    use_case: AssignCloudflareAccountManager = Depends(get_assign_manager),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Grant a user access to this account. OWNER only — only an existing
    OWNER (or manage_all) can hand out access to someone else."""
    await use_case.execute(
        account_id, body.user_id, body.access_level, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[None](success=True)


@router.patch("/cloudflare-accounts/{account_id}/managers/{user_id}")
async def update_cloudflare_account_manager(
    account_id: UUID,
    user_id: UUID,
    body: CloudflareAccountManagerUpdate,
    use_case: UpdateCloudflareAccountManager = Depends(get_update_manager),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Change a manager's access_level. Blocked if this would downgrade the
    last OWNER (same effect as removing them)."""
    await use_case.execute(
        account_id, user_id, body.access_level, actor_id=grant.user.id, actor_email=grant.user.email
    )
    return ApiResponse[None](success=True)


@router.delete("/cloudflare-accounts/{account_id}/managers/{user_id}")
async def remove_cloudflare_account_manager(
    account_id: UUID,
    user_id: UUID,
    use_case: RemoveCloudflareAccountManager = Depends(get_remove_manager),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.OWNER)),
) -> ApiResponse[None]:
    """Remove a user's access to this account. Blocked if they are the last OWNER."""
    await use_case.execute(account_id, user_id, actor_id=grant.user.id, actor_email=grant.user.email)
    return ApiResponse[None](success=True)
```

- [ ] **Step 4: Verify the router imports cleanly**

Run: `cd backend && uv run python -c "from app.modules.cloudflare.router import router; print(len(router.routes))"`
Expected: `10`

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/dependencies.py backend/app/modules/cloudflare/router.py
git commit -m "feat(cloudflare): add 10 router endpoints wired to Layer-1 + Layer-2 auth"
```

---

## Task 19: `public.py` shell + `main.py` registration + `.importlinter` retrofit

**Files:**
- Create: `backend/app/modules/cloudflare/public.py`
- Modify: `backend/app/main.py`
- Modify: `backend/.importlinter`

**Interfaces:**
- Produces: an importable (currently empty) `cloudflare.public` module satisfying `scripts/check_module_boundaries.py`'s convention that every module has one; the app registers `cloudflare_router` under the same `/api/v1` mounting every other module's router uses.

- [ ] **Step 1: Write `public.py`**

```python
"""Contract exposed to other modules. This is the ONLY file another module
may import from cloudflare — enforced by scripts/check_module_boundaries.py
and the cloudflare-facade contract in .importlinter.

Empty in Phase 3: no other module needs cross-module access to cloudflare
yet. Phase 4 (DNS binding) is expected to add a facade method here — e.g.
"resolve a ready CloudflareClient + decrypted token for an account_id" — so
DNS reaches Cloudflare through this facade instead of cloudflare's internals
directly.
"""

__all__: list[str] = []
```

- [ ] **Step 2: Register the router in `main.py`**

In `backend/app/main.py`, add the import alongside the existing module router imports (alphabetical, matching the existing block):

```python
from app.modules.cloudflare.router import router as cloudflare_router
```

Then find the existing `app.include_router(...)` calls (one per module, near the bottom of the file) and add one more following the exact same pattern as the others (same prefix, same call shape) — do not invent a different mounting convention.

- [ ] **Step 3: Add the `cloudflare-facade` contract and retrofit 3 existing contracts**

In `backend/.importlinter`, add a new contract (placed after the existing `audit-facade` stanza, before `common-is-a-leaf-module`):

```ini
[importlinter:contract:cloudflare-facade]
name = Other modules reach cloudflare only through public.py
type = forbidden
source_modules =
    app.modules.auth
    app.modules.rbac
    app.modules.users
    app.modules.projects
    app.modules.audit
    app.modules.common
forbidden_modules =
    app.modules.cloudflare.repository
    app.modules.cloudflare.models
    app.modules.cloudflare.uow
    app.modules.cloudflare.services
    app.modules.cloudflare.client
allow_indirect_imports = True
```

`client.py` is deliberately included in `forbidden_modules` — that is the entire reason it lives inside the module (see Task 5's docstring): later phases (DNS, Tunnels) must reach it through `cloudflare/public.py`, never directly.

Then edit the `source_modules` list of these 3 **existing** contracts to add `app.modules.cloudflare` (cloudflare imports all three of these modules' `public.py` — `rbac.public.require_permission`/`RbacApi`, `audit.public.AuditApi`, `users.public.UsersApi`/`UserRead` — and each contract's `source_modules` is a hardcoded list that does NOT auto-extend just because a new module exists):

- `rbac-facade`: add `app.modules.cloudflare` to `source_modules`.
- `audit-facade`: add `app.modules.cloudflare` to `source_modules`.
- `users-facade`: add `app.modules.cloudflare` to `source_modules` (this one is easy to miss — `app.modules.projects` isn't in `users-facade`'s list today either, because Phase 1 never needed `users.public`; Phase 3 is the first module that does).

- [ ] **Step 4: Verify import boundaries**

Run: `cd backend && lint-imports`
Expected: all contracts pass, including the 3 retrofitted ones and the new `cloudflare-facade` one.

Run: `cd backend && python scripts/check_module_boundaries.py --strict`
Expected: pass (this script auto-covers the new `cloudflare` folder — no manual registration needed here, unlike `.importlinter`).

- [ ] **Step 5: Verify the app boots**

Run: `cd backend && uv run python -c "from app.main import app; print([r.path for r in app.routes if 'cloudflare' in r.path])"`
Expected: prints all 10 `/api/v1/cloudflare-accounts...` paths.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/cloudflare/public.py backend/app/main.py backend/.importlinter
git commit -m "feat(cloudflare): register router and retrofit .importlinter facade contracts"
```

---

## Task 20: Router integration tests (real Postgres, faked Cloudflare API)

**Files:**
- Create: `backend/tests/cloudflare/test_router.py`

**Interfaces:**
- Consumes: the `client`/`engine` fixtures from `backend/tests/conftest.py`, the `_login_with_permissions`-style helper pattern from `backend/tests/audit/test_router.py`, `get_cloudflare_client` (Task 8) overridden via `app.dependency_overrides` so no real network call is made.
- Verifies the master-plan Phase 3 demo script end-to-end against real HTTP + real Postgres: create with a fake-but-successful token, reject a bad token, list-filtering excludes an unrelated user, and the last-owner guard fires over real HTTP (not just at the unit level).

- [ ] **Step 1: Write the tests**

```python
"""Integration tests for app.modules.cloudflare.router — real Postgres via
testcontainers, Cloudflare API calls faked via a dependency override."""

from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.main import app
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.cloudflare.dependencies import get_cloudflare_client
from app.modules.cloudflare.exceptions import InvalidCloudflareToken
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


class FakeCloudflareClient:
    """Overrides the real CloudflareClient for the duration of one test —
    no test in this file makes a real network call."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises

    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        if self._raises is not None:
            raise self._raises


async def _login_with_permissions(
    client: AsyncClient,
    engine: AsyncEngine,
    *,
    permissions: list[tuple[str, str]],
    email: str = "actor@example.com",
) -> UUID:
    """Create a user with a fresh role granting exactly `permissions`, then
    authenticate `client` as them. Mirrors tests/audit/test_router.py's
    helper of the same name and shape."""
    async with engine.begin() as conn:
        user_result = await conn.execute(
            insert(User).values(
                email=email,
                name=email,
                status="active",
                external_user_id=f"dx-{email}",
                employee_code=None,
                email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]
        role_result = await conn.execute(insert(Role).values(name=f"role-{email}", is_system=False))
        role_id = role_result.inserted_primary_key[0]
        for resource, action in permissions:
            perm_result = await conn.execute(
                insert(Permission).values(resource=resource, action=action, description_key="x")
            )
            permission_id = perm_result.inserted_primary_key[0]
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))
        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": f"test-jti-{email}"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


MANAGE_AND_VIEW = [("cloudflare_account", "manage"), ("cloudflare_account", "view")]


class TestCreateCloudflareAccount:
    async def test_creates_account_response_never_includes_token(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW)

        response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - Customer A", "cfAccountId": "cf-1", "apiToken": "real-token"},
        )

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["label"] == "CF - Customer A"
        assert "apiToken" not in body
        assert "api_token" not in body

        del app.dependency_overrides[get_cloudflare_client]

    async def test_rejects_bad_token_with_no_row_persisted(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient(
            raises=InvalidCloudflareToken()
        )
        await _login_with_permissions(client, engine, permissions=[("cloudflare_account", "manage")])

        response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - Bad", "cfAccountId": "cf-2", "apiToken": "bad-token"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cloudflare_invalid_token"

        del app.dependency_overrides[get_cloudflare_client]

    async def test_requires_manage_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "X", "cfAccountId": "cf-3", "apiToken": "x"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"


class TestListCloudflareAccountsFiltering:
    async def test_user_with_no_relationship_sees_empty_list_not_403(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW, email="owner@example.com")
        await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - Owner's", "cfAccountId": "cf-1", "apiToken": "x"},
        )

        await _login_with_permissions(
            client, engine, permissions=[("cloudflare_account", "view")], email="outsider@example.com"
        )
        response = await client.get("/api/v1/cloudflare-accounts")

        assert response.status_code == 200
        assert response.json()["data"] == []

        del app.dependency_overrides[get_cloudflare_client]


class TestRevealTokenAccessLevel:
    async def test_viewer_manager_cannot_reveal_token(self, client: AsyncClient, engine: AsyncEngine) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW, email="owner@example.com")
        create_response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"},
        )
        account_id = create_response.json()["data"]["id"]
        viewer_id = await _login_with_permissions(
            client, engine, permissions=MANAGE_AND_VIEW, email="viewer@example.com"
        )
        # Re-authenticate as owner to assign the viewer (assign requires OWNER)
        await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW, email="owner2@example.com")

        del app.dependency_overrides[get_cloudflare_client]


class TestLastOwnerGuardViaRouter:
    async def test_delete_manager_blocked_for_last_owner(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        owner_id = await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW)
        create_response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"},
        )
        account_id = create_response.json()["data"]["id"]

        response = await client.delete(f"/api/v1/cloudflare-accounts/{account_id}/managers/{owner_id}")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "cloudflare_last_owner_removal_blocked"

        del app.dependency_overrides[get_cloudflare_client]

    async def test_downgrade_manager_blocked_for_last_owner(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        owner_id = await _login_with_permissions(client, engine, permissions=MANAGE_AND_VIEW)
        create_response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"},
        )
        account_id = create_response.json()["data"]["id"]

        response = await client.patch(
            f"/api/v1/cloudflare-accounts/{account_id}/managers/{owner_id}",
            json={"accessLevel": "editor"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "cloudflare_last_owner_removal_blocked"

        del app.dependency_overrides[get_cloudflare_client]
```

- [ ] **Step 2: Delete the incomplete `TestRevealTokenAccessLevel` stub above and replace it with a real assertion**

The multi-user re-authentication needed for a full "assign a VIEWER, then log in as them, then try to reveal" flow is easiest to get right by inlining it directly rather than through the shared helper (each `_login_with_permissions` call replaces `client.cookies`, so the OWNER's session is gone by the time you'd act as them again). Replace the stub with:

```python
class TestRevealTokenAccessLevel:
    async def test_viewer_manager_cannot_reveal_token(self, client: AsyncClient, engine: AsyncEngine) -> None:
        app.dependency_overrides[get_cloudflare_client] = lambda: FakeCloudflareClient()
        owner_id = await _login_with_permissions(
            client, engine, permissions=MANAGE_AND_VIEW, email="owner@example.com"
        )
        create_response = await client.post(
            "/api/v1/cloudflare-accounts",
            json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"},
        )
        account_id = create_response.json()["data"]["id"]

        viewer_id = await _login_with_permissions(
            client, engine, permissions=[("cloudflare_account", "view")], email="viewer@example.com"
        )
        # Re-authenticate as the owner (their own cookie was overwritten
        # above) so they, not the viewer, perform the assignment.
        token = JwtCodec.encode(
            {"sub": str(owner_id), "type": "access", "jti": "owner-again"},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
        assign_response = await client.post(
            f"/api/v1/cloudflare-accounts/{account_id}/managers",
            json={"userId": str(viewer_id), "accessLevel": "viewer"},
        )
        assert assign_response.status_code == 200

        # Switch back to the viewer and attempt to reveal the token.
        viewer_token = JwtCodec.encode(
            {"sub": str(viewer_id), "type": "access", "jti": "viewer-again"},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, viewer_token)

        response = await client.post(f"/api/v1/cloudflare-accounts/{account_id}/reveal-token")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "cloudflare_insufficient_account_access"

        del app.dependency_overrides[get_cloudflare_client]
```

- [ ] **Step 3: Run all router tests**

Run: `cd backend && uv run pytest tests/cloudflare/test_router.py -v`
Expected: PASS (8 tests)

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q`
Expected: all green. This is the same command the Global Constraints and the plan's Test/Verify Checklist require before moving to Phase 4.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/cloudflare/test_router.py
git commit -m "test(cloudflare): add router integration tests covering the Phase 3 demo script"
```

---

## Task 21: `entities/cloudflare-account/` (frontend, read-only)

**Files:**
- Create: `frontend/src/entities/cloudflare-account/model/schema.ts`
- Create: `frontend/src/entities/cloudflare-account/api/query-keys.ts`
- Create: `frontend/src/entities/cloudflare-account/api/fetchers.ts`
- Create: `frontend/src/entities/cloudflare-account/hooks/use-cloudflare-accounts.ts`
- Create: `frontend/src/entities/cloudflare-account/index.ts`

**Interfaces:**
- Mirrors `entities/environment/` exactly (unpaginated `.array().parse(raw)` — `GET /cloudflare-accounts` returns a bare list, not a `Page[...]`, unlike `entities/project`'s paginated shape).
- Produces: `CloudflareAccount` type, `cloudflareAccountSchema`, `cloudflareAccountsKeys.{all,lists,list,detail}`, `fetchCloudflareAccounts()`, `fetchCloudflareAccount(id)`, `useCloudflareAccountsQuery()`, `useCloudflareAccountQuery(id)`. Task 23's mutation hooks invalidate via `cloudflareAccountsKeys.all`/`.detail(id)`; Task 24/25's UI components consume the two query hooks.

- [ ] **Step 1: Write `model/schema.ts`**

```ts
import { z } from "zod";

export const cloudflareAccountSchema = z.object({
  id: z.uuid(),
  label: z.string(),
  cfAccountId: z.string(),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type CloudflareAccount = z.infer<typeof cloudflareAccountSchema>;
```

- [ ] **Step 2: Write `api/query-keys.ts`**

```ts
/**
 * Hierarchical query key factory for the cloudflare-account entity.
 */
export const cloudflareAccountsKeys = {
  all: ["cloudflare-accounts"] as const,
  lists: () => [...cloudflareAccountsKeys.all, "list"] as const,
  list: () => [...cloudflareAccountsKeys.lists()] as const,
  detail: (id: string) => [...cloudflareAccountsKeys.all, "detail", id] as const,
};
```

- [ ] **Step 3: Write `api/fetchers.ts`**

```ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { cloudflareAccountSchema, type CloudflareAccount } from "../model/schema";

/**
 * Fetches every Cloudflare account visible to the current user from
 * GET /cloudflare-accounts (already filtered server-side).
 */
export async function fetchCloudflareAccounts(): Promise<CloudflareAccount[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ROOT);
  return cloudflareAccountSchema.array().parse(raw);
}

/**
 * Fetches one Cloudflare account from GET /cloudflare-accounts/{id}.
 */
export async function fetchCloudflareAccount(id: string): Promise<CloudflareAccount> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.DETAIL(id));
  return cloudflareAccountSchema.parse(raw);
}
```

- [ ] **Step 4: Write `hooks/use-cloudflare-accounts.ts`**

```ts
"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchCloudflareAccount, fetchCloudflareAccounts } from "../api/fetchers";
import { cloudflareAccountsKeys } from "../api/query-keys";

export function useCloudflareAccountsQuery() {
  return useSuspenseQuery({
    queryKey: cloudflareAccountsKeys.list(),
    queryFn: () => fetchCloudflareAccounts(),
  });
}

export function useCloudflareAccountQuery(id: string) {
  return useSuspenseQuery({
    queryKey: cloudflareAccountsKeys.detail(id),
    queryFn: () => fetchCloudflareAccount(id),
  });
}
```

- [ ] **Step 5: Write `index.ts`**

```ts
export { fetchCloudflareAccounts, fetchCloudflareAccount } from "./api/fetchers";
export { cloudflareAccountsKeys } from "./api/query-keys";
export { useCloudflareAccountsQuery, useCloudflareAccountQuery } from "./hooks/use-cloudflare-accounts";
export { cloudflareAccountSchema } from "./model/schema";
export type { CloudflareAccount } from "./model/schema";
```

- [ ] **Step 6: Verify the entity compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (Task 22 wires `API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS`, so this step may still show a missing-property error until Task 22 lands — that is expected and resolved there, not here).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/entities/cloudflare-account
git commit -m "feat(cloudflare-accounts): add entities/cloudflare-account read layer"
```

---

## Task 22: Shared constants (`permissions.ts`, `routes.ts`, `api.ts`) + i18n wiring

**Files:**
- Modify: `frontend/src/shared/constants/permissions.ts`
- Modify: `frontend/src/shared/constants/routes.ts`
- Modify: `frontend/src/shared/constants/api.ts`
- Create: `frontend/locales/en/modules/cloudflare-accounts.json`
- Create: `frontend/locales/vi/modules/cloudflare-accounts.json`
- Modify: `frontend/src/shared/lib/i18n/request.ts`

**Interfaces:**
- Produces: `RESOURCES.CLOUDFLARE_ACCOUNT`, `ACTIONS.VIEW`/`ACTIONS.MANAGE` (new — the backend's actual two Layer-1 actions; deliberately NOT a 4-action CRUD illusion the backend doesn't have), `PERMISSIONS.CLOUDFLARE_ACCOUNT.{RESOURCE,VIEW,MANAGE}`, `ROUTES.adminCloudflareAccounts`, `API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.{ROOT,DETAIL,TEST_CONNECTION,REVEAL_TOKEN,MANAGERS,MANAGER_DETAIL}`, `cloudflareAccounts` i18n namespace. Every later frontend task depends on these exact names.

- [ ] **Step 1: Add `VIEW`/`MANAGE` actions and the `CLOUDFLARE_ACCOUNT` resource/permission block**

In `frontend/src/shared/constants/permissions.ts`, add to `RESOURCES`:

```ts
  CLOUDFLARE_ACCOUNT: "cloudflare_account",
```

Add to `ACTIONS` (the backend's Layer-1 actions for this module are literally `view`/`manage`, not the CRUD-shaped `read`/`create`/`update`/`delete` every other resource uses — keep the frontend honest about that instead of inventing a mapping the backend doesn't have):

```ts
  VIEW: "view",
  MANAGE: "manage",
```

Add to `PERMISSIONS`:

```ts
  CLOUDFLARE_ACCOUNT: {
    RESOURCE: RESOURCES.CLOUDFLARE_ACCOUNT,
    VIEW: `${RESOURCES.CLOUDFLARE_ACCOUNT}.${ACTIONS.VIEW}` as const,
    MANAGE: `${RESOURCES.CLOUDFLARE_ACCOUNT}.${ACTIONS.MANAGE}` as const,
  },
```

- [ ] **Step 2: Add the route**

In `frontend/src/shared/constants/routes.ts`, add:

```ts
  adminCloudflareAccounts: "/admin/cloudflare-accounts",
```

- [ ] **Step 3: Add the API endpoint block**

In `frontend/src/shared/constants/api.ts`, add inside `API_CONFIG.ENDPOINTS`, alongside `PROJECTS`:

```ts
    CLOUDFLARE_ACCOUNTS: {
      ROOT: "/cloudflare-accounts",
      DETAIL: (id: string) => `/cloudflare-accounts/${id}`,
      TEST_CONNECTION: (id: string) => `/cloudflare-accounts/${id}/test-connection`,
      REVEAL_TOKEN: (id: string) => `/cloudflare-accounts/${id}/reveal-token`,
      MANAGERS: (id: string) => `/cloudflare-accounts/${id}/managers`,
      MANAGER_DETAIL: (id: string, userId: string) => `/cloudflare-accounts/${id}/managers/${userId}`,
    },
```

- [ ] **Step 4: Write `locales/en/modules/cloudflare-accounts.json`**

```json
{
  "title": "Cloudflare Accounts",
  "description": "Manage Cloudflare account credentials and who can access them.",
  "createAccount": "New Account",
  "editAccount": "Edit Account",
  "empty": "No Cloudflare accounts yet.",
  "table": {
    "label": "Label",
    "cfAccountId": "Cloudflare Account ID",
    "createdAt": "Created",
    "actions": "Actions"
  },
  "actions": {
    "testConnection": "Test Connection",
    "testConnectionSuccess": "Connection succeeded.",
    "revealToken": "Reveal Token",
    "hideToken": "Hide Token",
    "copyToken": "Copy",
    "manageAccess": "Manage Access"
  },
  "form": {
    "label": "Label",
    "cfAccountId": "Cloudflare Account ID",
    "apiToken": "API Token",
    "apiTokenHint": "Cloudflare must accept this token before the account can be saved.",
    "rotateToken": "Rotate token",
    "cancel": "Cancel",
    "save": "Save",
    "create": "Create",
    "saving": "Saving..."
  },
  "deleteConfirm": {
    "title": "Delete Cloudflare account?",
    "description": "This cannot be undone. Any environment binding using this account (Phase 4) will break."
  },
  "managers": {
    "title": "Managers",
    "empty": "No one has been granted access to this account yet.",
    "assign": "Assign Manager",
    "user": "User",
    "accessLevel": "Access Level",
    "levels": {
      "owner": "Owner",
      "editor": "Editor",
      "viewer": "Viewer"
    },
    "removeConfirm": {
      "title": "Remove this manager?",
      "description": "They will lose all access to this account."
    }
  },
  "errors": {
    "cloudflare_account_not_found": "This Cloudflare account no longer exists.",
    "cloudflare_account_manager_not_found": "This manager no longer exists.",
    "cloudflare_invalid_token": "Cloudflare rejected this API token.",
    "cloudflare_api_unavailable": "Could not reach Cloudflare. Try again shortly.",
    "cloudflare_insufficient_account_access": "You don't have sufficient access on this account.",
    "cloudflare_last_owner_removal_blocked": "You can't remove or downgrade the last owner of this account."
  }
}
```

- [ ] **Step 5: Write `locales/vi/modules/cloudflare-accounts.json`**

```json
{
  "title": "Tài khoản Cloudflare",
  "description": "Quản lý thông tin đăng nhập tài khoản Cloudflare và quyền truy cập.",
  "createAccount": "Thêm tài khoản",
  "editAccount": "Sửa tài khoản",
  "empty": "Chưa có tài khoản Cloudflare nào.",
  "table": {
    "label": "Tên gợi nhớ",
    "cfAccountId": "Cloudflare Account ID",
    "createdAt": "Ngày tạo",
    "actions": "Thao tác"
  },
  "actions": {
    "testConnection": "Kiểm tra kết nối",
    "testConnectionSuccess": "Kết nối thành công.",
    "revealToken": "Xem token",
    "hideToken": "Ẩn token",
    "copyToken": "Sao chép",
    "manageAccess": "Quản lý quyền truy cập"
  },
  "form": {
    "label": "Tên gợi nhớ",
    "cfAccountId": "Cloudflare Account ID",
    "apiToken": "API Token",
    "apiTokenHint": "Cloudflare phải chấp nhận token này trước khi lưu tài khoản.",
    "rotateToken": "Đổi token",
    "cancel": "Hủy",
    "save": "Lưu",
    "create": "Tạo",
    "saving": "Đang lưu..."
  },
  "deleteConfirm": {
    "title": "Xóa tài khoản Cloudflare?",
    "description": "Không thể hoàn tác. Mọi environment đang gắn với account này (Phase 4) sẽ bị lỗi."
  },
  "managers": {
    "title": "Người quản lý",
    "empty": "Chưa có ai được cấp quyền truy cập tài khoản này.",
    "assign": "Gán người quản lý",
    "user": "Người dùng",
    "accessLevel": "Cấp độ truy cập",
    "levels": {
      "owner": "Chủ sở hữu",
      "editor": "Biên tập",
      "viewer": "Chỉ xem"
    },
    "removeConfirm": {
      "title": "Xóa người quản lý này?",
      "description": "Họ sẽ mất toàn bộ quyền truy cập tài khoản này."
    }
  },
  "errors": {
    "cloudflare_account_not_found": "Tài khoản Cloudflare này không còn tồn tại.",
    "cloudflare_account_manager_not_found": "Người quản lý này không còn tồn tại.",
    "cloudflare_invalid_token": "Cloudflare từ chối API token này.",
    "cloudflare_api_unavailable": "Không thể kết nối Cloudflare. Vui lòng thử lại sau.",
    "cloudflare_insufficient_account_access": "Bạn không có đủ quyền trên tài khoản này.",
    "cloudflare_last_owner_removal_blocked": "Không thể xóa hoặc hạ quyền chủ sở hữu cuối cùng của tài khoản này."
  }
}
```

- [ ] **Step 6: Register the namespace in `request.ts`**

In `frontend/src/shared/lib/i18n/request.ts`, add `cloudflareAccounts` to both the `Promise.all` import array and the returned `messages` object, following the exact pattern `auditLog` already uses:

```ts
  const [common, auth, users, roles, projects, auditLog, cloudflareAccounts] = await Promise.all([
    import(`../../../../locales/${locale}/common.json`),
    import(`../../../../locales/${locale}/modules/auth.json`),
    import(`../../../../locales/${locale}/modules/users.json`),
    import(`../../../../locales/${locale}/modules/roles.json`),
    import(`../../../../locales/${locale}/modules/projects.json`),
    import(`../../../../locales/${locale}/modules/audit-log.json`),
    import(`../../../../locales/${locale}/modules/cloudflare-accounts.json`),
  ]);

  return {
    locale,
    messages: {
      common: common.default,
      auth: auth.default,
      users: users.default,
      roles: roles.default,
      projects: projects.default,
      auditLog: auditLog.default,
      cloudflareAccounts: cloudflareAccounts.default,
    },
  };
```

- [ ] **Step 7: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: Task 21's entity now compiles cleanly (`API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS` now exists).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/shared/constants/permissions.ts frontend/src/shared/constants/routes.ts frontend/src/shared/constants/api.ts frontend/locales/en/modules/cloudflare-accounts.json frontend/locales/vi/modules/cloudflare-accounts.json frontend/src/shared/lib/i18n/request.ts
git commit -m "feat(cloudflare-accounts): wire shared constants and i18n namespace"
```

---

## Task 23: `modules/cloudflare-accounts/` — fetchers + mutation/query hooks

**Files:**
- Create: `frontend/src/modules/cloudflare-accounts/api/fetchers.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-create-cloudflare-account.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-update-cloudflare-account.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-delete-cloudflare-account.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-test-cloudflare-account-connection.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-reveal-cloudflare-account-token.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-cloudflare-account-managers.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-assign-cloudflare-account-manager.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-update-cloudflare-account-manager.ts`
- Create: `frontend/src/modules/cloudflare-accounts/hooks/use-remove-cloudflare-account-manager.ts`

**Interfaces:**
- Consumes: `cloudflareAccountsKeys` from `@/entities/cloudflare-account` (Task 21), `API_CONFIG` (Task 22).
- Produces: `CloudflareAccountManager` type + `AccessLevel` type (module-owned, no dedicated entity — mirrors how `ProjectLink` lives in `modules/projects`, not a separate entity, per the Explore report); every mutation hook below (`useCreateCloudflareAccount`, `useUpdateCloudflareAccount`, `useDeleteCloudflareAccount`, `useTestCloudflareAccountConnection`, `useRevealCloudflareAccountToken`, `useAssignCloudflareAccountManager`, `useUpdateCloudflareAccountManager`, `useRemoveCloudflareAccountManager`) and one query hook (`useCloudflareAccountManagersQuery(accountId)`). Task 24/25's dialogs and views consume these exact hook names.

- [ ] **Step 1: Write `api/fetchers.ts`**

```ts
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import type { CloudflareAccount } from "@/entities/cloudflare-account";

export async function createCloudflareAccount(data: {
  label: string;
  cfAccountId: string;
  apiToken: string;
}): Promise<CloudflareAccount> {
  return apiFetch<CloudflareAccount>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ROOT, {
    method: "POST",
    data,
  });
}

export async function updateCloudflareAccount(
  id: string,
  data: { label?: string; apiToken?: string },
): Promise<CloudflareAccount> {
  return apiFetch<CloudflareAccount>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.DETAIL(id), {
    method: "PATCH",
    data,
  });
}

export async function deleteCloudflareAccount(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.DETAIL(id), { method: "DELETE" });
}

export async function testCloudflareAccountConnection(id: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.TEST_CONNECTION(id), { method: "POST" });
}

export async function revealCloudflareAccountToken(id: string): Promise<string> {
  const result = await apiFetch<{ apiToken: string }>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.REVEAL_TOKEN(id),
    { method: "POST" },
  );
  return result.apiToken;
}

export type AccessLevel = "owner" | "editor" | "viewer";

export interface CloudflareAccountManager {
  userId: string;
  email: string;
  name: string;
  accessLevel: AccessLevel;
  createdAt: string;
}

export async function fetchCloudflareAccountManagers(accountId: string): Promise<CloudflareAccountManager[]> {
  return apiFetch<CloudflareAccountManager[]>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGERS(accountId));
}

export async function assignCloudflareAccountManager(
  accountId: string,
  data: { userId: string; accessLevel: AccessLevel },
): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGERS(accountId), {
    method: "POST",
    data,
  });
}

export async function updateCloudflareAccountManager(
  accountId: string,
  userId: string,
  data: { accessLevel: AccessLevel },
): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGER_DETAIL(accountId, userId), {
    method: "PATCH",
    data,
  });
}

export async function removeCloudflareAccountManager(accountId: string, userId: string): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.MANAGER_DETAIL(accountId, userId), {
    method: "DELETE",
  });
}
```

- [ ] **Step 2: Write the account-level mutation hooks**

`hooks/use-create-cloudflare-account.ts`:

```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createCloudflareAccount } from "../api/fetchers";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";

export function useCreateCloudflareAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { label: string; cfAccountId: string; apiToken: string }) =>
      createCloudflareAccount(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.all });
    },
  });
}
```

`hooks/use-update-cloudflare-account.ts`:

```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateCloudflareAccount } from "../api/fetchers";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";

export function useUpdateCloudflareAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { label?: string; apiToken?: string } }) =>
      updateCloudflareAccount(id, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.all });
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.detail(variables.id) });
    },
  });
}
```

`hooks/use-delete-cloudflare-account.ts`:

```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteCloudflareAccount } from "../api/fetchers";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";

export function useDeleteCloudflareAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteCloudflareAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountsKeys.all });
    },
  });
}
```

`hooks/use-test-cloudflare-account-connection.ts`:

```ts
"use client";

import { useMutation } from "@tanstack/react-query";
import { testCloudflareAccountConnection } from "../api/fetchers";

export function useTestCloudflareAccountConnection() {
  return useMutation({
    mutationFn: (id: string) => testCloudflareAccountConnection(id),
  });
}
```

`hooks/use-reveal-cloudflare-account-token.ts`:

```ts
"use client";

import { useMutation } from "@tanstack/react-query";
import { revealCloudflareAccountToken } from "../api/fetchers";

export function useRevealCloudflareAccountToken() {
  return useMutation({
    mutationFn: (id: string) => revealCloudflareAccountToken(id),
  });
}
```

- [ ] **Step 3: Write the manager query + mutation hooks**

`hooks/use-cloudflare-account-managers.ts`:

```ts
"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchCloudflareAccountManagers } from "../api/fetchers";

export const cloudflareAccountManagersKeys = {
  forAccount: (accountId: string) => ["cloudflare-accounts", "managers", accountId] as const,
};

export function useCloudflareAccountManagersQuery(accountId: string) {
  return useSuspenseQuery({
    queryKey: cloudflareAccountManagersKeys.forAccount(accountId),
    queryFn: () => fetchCloudflareAccountManagers(accountId),
  });
}
```

`hooks/use-assign-cloudflare-account-manager.ts`:

```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { assignCloudflareAccountManager, type AccessLevel } from "../api/fetchers";
import { cloudflareAccountManagersKeys } from "./use-cloudflare-account-managers";

export function useAssignCloudflareAccountManager(accountId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { userId: string; accessLevel: AccessLevel }) =>
      assignCloudflareAccountManager(accountId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountManagersKeys.forAccount(accountId) });
    },
  });
}
```

`hooks/use-update-cloudflare-account-manager.ts`:

```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateCloudflareAccountManager, type AccessLevel } from "../api/fetchers";
import { cloudflareAccountManagersKeys } from "./use-cloudflare-account-managers";

export function useUpdateCloudflareAccountManager(accountId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, accessLevel }: { userId: string; accessLevel: AccessLevel }) =>
      updateCloudflareAccountManager(accountId, userId, { accessLevel }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountManagersKeys.forAccount(accountId) });
    },
  });
}
```

`hooks/use-remove-cloudflare-account-manager.ts`:

```ts
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { removeCloudflareAccountManager } from "../api/fetchers";
import { cloudflareAccountManagersKeys } from "./use-cloudflare-account-managers";

export function useRemoveCloudflareAccountManager(accountId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) => removeCloudflareAccountManager(accountId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareAccountManagersKeys.forAccount(accountId) });
    },
  });
}
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/cloudflare-accounts/api frontend/src/modules/cloudflare-accounts/hooks
git commit -m "feat(cloudflare-accounts): add module fetchers and mutation/query hooks"
```

---

## Task 24: List page UI — `cloudflare-accounts-page-content.tsx` + `cloudflare-account-form-dialog.tsx`

**MANDATORY per AGENTS.md Phase 3 rule:** this task writes UI markup (layout, table, dialog, color, spacing) — invoke the `ui-ux-pro-max` plugin while implementing it (query its style/palette/a11y database and apply the result), same as every other UI surface in this repo. The code below mirrors `modules/projects/ui/projects-page-content.tsx` and `project-form-dialog.tsx` structurally; treat their actual on-disk styling as the source of truth for exact Tailwind tokens/spacing where this plan's version differs.

**Files:**
- Create: `frontend/src/modules/cloudflare-accounts/ui/cloudflare-accounts-page-content.tsx`
- Create: `frontend/src/modules/cloudflare-accounts/ui/cloudflare-account-form-dialog.tsx`
- Create: `frontend/src/modules/cloudflare-accounts/index.ts`

**Interfaces:**
- Consumes: `useCloudflareAccountsQuery` (Task 21), `useCreateCloudflareAccount`/`useUpdateCloudflareAccount`/`useDeleteCloudflareAccount` (Task 23), `Can`/`ConfirmDialog`/`Button`/`Input`/`Label` (existing `shared/ui`/`entities/permission`), `useApiErrorMessage` (existing `shared/lib/handle-api-error`).
- Produces: `CloudflareAccountsPageContent` (exported from the module's `index.ts`) — Task 26's list route renders this.

- [ ] **Step 1: Write `ui/cloudflare-account-form-dialog.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, Cloud } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import type { CloudflareAccount } from "@/entities/cloudflare-account";
import { useCreateCloudflareAccount } from "../hooks/use-create-cloudflare-account";
import { useUpdateCloudflareAccount } from "../hooks/use-update-cloudflare-account";

interface CloudflareAccountFormDialogProps {
  account: CloudflareAccount | null;
  onClose: () => void;
}

export function CloudflareAccountFormDialog({ account, onClose }: CloudflareAccountFormDialogProps) {
  const t = useTranslations("cloudflareAccounts");
  const isEditing = Boolean(account);
  const [label, setLabel] = useState(account?.label ?? "");
  const [cfAccountId, setCfAccountId] = useState(account?.cfAccountId ?? "");
  const [apiToken, setApiToken] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const getErrorMessage = useApiErrorMessage("cloudflareAccounts");

  const create = useCreateCloudflareAccount();
  const update = useUpdateCloudflareAccount();
  const isSaving = create.isPending || update.isPending;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };
    if (isEditing && account) {
      update.mutate({ id: account.id, data: { label, apiToken: apiToken || undefined } }, callbacks);
    } else {
      create.mutate({ label, cfAccountId, apiToken }, callbacks);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg animate-in zoom-in-95">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-md bg-primary/10">
              <Cloud className="size-4 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">{isEditing ? t("editAccount") : t("createAccount")}</h2>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {errorMessage && (
            <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="label">{t("form.label")}</Label>
            <Input id="label" value={label} onChange={(e) => setLabel(e.target.value)} required />
          </div>

          {!isEditing && (
            <div className="space-y-1.5">
              <Label htmlFor="cfAccountId">{t("form.cfAccountId")}</Label>
              <Input
                id="cfAccountId"
                value={cfAccountId}
                onChange={(e) => setCfAccountId(e.target.value)}
                required
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="apiToken">{isEditing ? t("form.rotateToken") : t("form.apiToken")}</Label>
            <Input
              id="apiToken"
              type="password"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              required={!isEditing}
            />
            <p className="text-xs text-muted-foreground">{t("form.apiTokenHint")}</p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `ui/cloudflare-accounts-page-content.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { Plus, Pencil, Trash2, Cloud } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ROUTES } from "@/shared/constants/routes";
import { PERMISSIONS } from "@/shared/constants/permissions";
import { useCloudflareAccountsQuery, type CloudflareAccount } from "@/entities/cloudflare-account";
import { useDeleteCloudflareAccount } from "../hooks/use-delete-cloudflare-account";
import { CloudflareAccountFormDialog } from "./cloudflare-account-form-dialog";

export function CloudflareAccountsPageContent() {
  const t = useTranslations("cloudflareAccounts");
  const { data: accounts } = useCloudflareAccountsQuery();
  const deleteAccount = useDeleteCloudflareAccount();

  const [formTarget, setFormTarget] = useState<CloudflareAccount | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CloudflareAccount | null>(null);

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <Can I="manage" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
          <Button onClick={() => setFormTarget("create")}>
            <Plus className="size-4" />
            {t("createAccount")}
          </Button>
        </Can>
      </div>

      {accounts.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16 text-center">
          <Cloud className="size-10 text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">{t("table.label")}</th>
                <th className="px-4 py-3 font-medium">{t("table.cfAccountId")}</th>
                <th className="px-4 py-3 font-medium">{t("table.createdAt")}</th>
                <th className="px-4 py-3 font-medium text-right">{t("table.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {accounts.map((account) => (
                <tr key={account.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <Link
                      href={`${ROUTES.adminCloudflareAccounts}/${account.id}`}
                      className="font-medium text-foreground hover:underline"
                    >
                      {account.label}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{account.cfAccountId}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(account.createdAt).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <Can I="manage" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                        <Button variant="ghost" size="icon-sm" onClick={() => setFormTarget(account)}>
                          <Pencil className="size-4" />
                        </Button>
                        <Button variant="ghost" size="icon-sm" onClick={() => setDeleteTarget(account)}>
                          <Trash2 className="size-4 text-destructive" />
                        </Button>
                      </Can>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {formTarget !== null && (
        <CloudflareAccountFormDialog
          account={formTarget === "create" ? null : formTarget}
          onClose={() => setFormTarget(null)}
        />
      )}

      {deleteTarget !== null && (
        <ConfirmDialog
          isOpen
          onClose={() => setDeleteTarget(null)}
          onConfirm={async () => {
            await deleteAccount.mutateAsync(deleteTarget.id);
            setDeleteTarget(null);
          }}
          title={t("deleteConfirm.title")}
          description={t("deleteConfirm.description")}
          variant="destructive"
          isLoading={deleteAccount.isPending}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Write `index.ts`**

```ts
export { CloudflareAccountsPageContent } from "./ui/cloudflare-accounts-page-content";
```

(Task 25 appends `CloudflareAccountDetailView` to this same file.)

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (Task 26's route files are what actually render this component — expect no route wiring yet).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/cloudflare-accounts/ui/cloudflare-accounts-page-content.tsx frontend/src/modules/cloudflare-accounts/ui/cloudflare-account-form-dialog.tsx frontend/src/modules/cloudflare-accounts/index.ts
git commit -m "feat(cloudflare-accounts): add list page UI and account form dialog"
```

---

## Task 25: Detail view UI — `cloudflare-account-detail-view.tsx` + `cloudflare-account-manager-form-dialog.tsx`

**MANDATORY per AGENTS.md Phase 3 rule:** invoke `ui-ux-pro-max` while implementing this task, same as Task 24 — this is the reveal-token affordance, the single most security-sensitive UI surface in this phase, so contrast/focus-state/a11y guidance matters more here than almost anywhere else in the module (a revealed secret must be unmistakably distinguishable from a masked one, and the copy action must be keyboard reachable).

**Files:**
- Create: `frontend/src/modules/cloudflare-accounts/ui/cloudflare-account-manager-form-dialog.tsx`
- Create: `frontend/src/modules/cloudflare-accounts/ui/cloudflare-account-detail-view.tsx`
- Modify: `frontend/src/modules/cloudflare-accounts/index.ts` (append `CloudflareAccountDetailView` export)

**Interfaces:**
- Consumes: `useCloudflareAccountQuery` (Task 21), `useTestCloudflareAccountConnection`/`useRevealCloudflareAccountToken`/`useCloudflareAccountManagersQuery`/`useAssignCloudflareAccountManager`/`useRemoveCloudflareAccountManager` (Task 23).
- Produces: `CloudflareAccountDetailView({ accountId })` — Task 26's detail route renders this. The reveal-token flow keeps the plaintext only in local component state, cleared whenever the toggle is pressed again or the dialog/page unmounts — never persisted to a query cache (Task 23's `useRevealCloudflareAccountToken` is a `useMutation`, not a `useQuery`, specifically so React Query never caches the secret).

- [ ] **Step 1: Write `ui/cloudflare-account-manager-form-dialog.tsx`**

Reuses the existing `GET /users` list endpoint for the user picker — no dedicated user-search component exists in `shared/ui` yet, so this is a small inline query rather than a new shared primitive (out of scope to build one for this phase).

```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { X, UserPlus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useAssignCloudflareAccountManager } from "../hooks/use-assign-cloudflare-account-manager";
import type { AccessLevel } from "../api/fetchers";

interface CloudflareAccountManagerFormDialogProps {
  accountId: string;
  onClose: () => void;
}

interface UserOption {
  id: string;
  email: string;
  name: string;
}

export function CloudflareAccountManagerFormDialog({
  accountId,
  onClose,
}: CloudflareAccountManagerFormDialogProps) {
  const t = useTranslations("cloudflareAccounts");
  const [userId, setUserId] = useState("");
  const [accessLevel, setAccessLevel] = useState<AccessLevel>("viewer");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const getErrorMessage = useApiErrorMessage("cloudflareAccounts");

  const { data: users } = useQuery({
    queryKey: ["users", "picker"],
    queryFn: () => apiFetch<{ items: UserOption[] }>(`${API_CONFIG.ENDPOINTS.USERS.ROOT}?limit=100`),
  });

  const assign = useAssignCloudflareAccountManager(accountId);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    assign.mutate(
      { userId, accessLevel },
      { onSuccess: () => onClose(), onError: (err) => setErrorMessage(getErrorMessage(err)) },
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg animate-in zoom-in-95">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-md bg-primary/10">
              <UserPlus className="size-4 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">{t("managers.assign")}</h2>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {errorMessage && (
            <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="userId">{t("managers.user")}</Label>
            <select
              id="userId"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              required
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="" disabled>
                —
              </option>
              {users?.items.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name} ({user.email})
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="accessLevel">{t("managers.accessLevel")}</Label>
            <select
              id="accessLevel"
              value={accessLevel}
              onChange={(e) => setAccessLevel(e.target.value as AccessLevel)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="viewer">{t("managers.levels.viewer")}</option>
              <option value="editor">{t("managers.levels.editor")}</option>
              <option value="owner">{t("managers.levels.owner")}</option>
            </select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={assign.isPending}>
              {assign.isPending ? t("form.saving") : t("form.save")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `ui/cloudflare-account-detail-view.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Cloud, ShieldCheck, Eye, EyeOff, UserPlus, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { PERMISSIONS } from "@/shared/constants/permissions";
import { useCloudflareAccountQuery } from "@/entities/cloudflare-account";
import { useTestCloudflareAccountConnection } from "../hooks/use-test-cloudflare-account-connection";
import { useRevealCloudflareAccountToken } from "../hooks/use-reveal-cloudflare-account-token";
import { useCloudflareAccountManagersQuery } from "../hooks/use-cloudflare-account-managers";
import { useRemoveCloudflareAccountManager } from "../hooks/use-remove-cloudflare-account-manager";
import { CloudflareAccountManagerFormDialog } from "./cloudflare-account-manager-form-dialog";

interface CloudflareAccountDetailViewProps {
  accountId: string;
}

export function CloudflareAccountDetailView({ accountId }: CloudflareAccountDetailViewProps) {
  const t = useTranslations("cloudflareAccounts");
  const { data: account } = useCloudflareAccountQuery(accountId);
  const { data: managers } = useCloudflareAccountManagersQuery(accountId);

  const testConnection = useTestCloudflareAccountConnection();
  const revealToken = useRevealCloudflareAccountToken();
  const removeManager = useRemoveCloudflareAccountManager(accountId);

  const [revealedToken, setRevealedToken] = useState<string | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  return (
    <div className="p-6 space-y-6">
      <section className="rounded-lg border border-border p-5">
        <div className="flex items-center gap-2 mb-4">
          <Cloud className="size-5 text-primary" />
          <h2 className="text-lg font-semibold">{account.label}</h2>
        </div>
        <dl className="grid grid-cols-2 gap-4 text-sm mb-4">
          <div>
            <dt className="text-muted-foreground">{t("table.cfAccountId")}</dt>
            <dd className="font-medium">{account.cfAccountId}</dd>
          </div>
        </dl>
        <div className="flex flex-wrap gap-2">
          <Can I="view" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button
              variant="outline"
              size="sm"
              onClick={() => testConnection.mutate(accountId)}
              disabled={testConnection.isPending}
            >
              <ShieldCheck className="size-4" />
              {t("actions.testConnection")}
            </Button>
          </Can>
          <Can I="manage" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                if (revealedToken) {
                  setRevealedToken(null);
                  return;
                }
                const token = await revealToken.mutateAsync(accountId);
                setRevealedToken(token);
              }}
              disabled={revealToken.isPending}
            >
              {revealedToken ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              {revealedToken ? t("actions.hideToken") : t("actions.revealToken")}
            </Button>
          </Can>
        </div>
        {testConnection.isSuccess && (
          <p className="mt-2 text-sm text-emerald-600">{t("actions.testConnectionSuccess")}</p>
        )}
        {revealedToken && (
          <div className="mt-3 flex items-center gap-2 rounded-md bg-muted px-3 py-2">
            <code className="text-xs break-all">{revealedToken}</code>
            <Button variant="ghost" size="icon-xs" onClick={() => navigator.clipboard.writeText(revealedToken)}>
              {t("actions.copyToken")}
            </Button>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-border p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">{t("managers.title")}</h3>
          <Can I="manage" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button variant="outline" size="sm" onClick={() => setAssignOpen(true)}>
              <UserPlus className="size-4" />
              {t("managers.assign")}
            </Button>
          </Can>
        </div>

        {managers.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("managers.empty")}</p>
        ) : (
          <ul className="divide-y divide-border">
            {managers.map((manager) => (
              <li key={manager.userId} className="flex items-center justify-between py-2 text-sm">
                <div>
                  <p className="font-medium">{manager.name}</p>
                  <p className="text-muted-foreground">{manager.email}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs uppercase text-muted-foreground">
                    {t(`managers.levels.${manager.accessLevel}`)}
                  </span>
                  <Can I="manage" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                    <Button variant="ghost" size="icon-xs" onClick={() => setRemoveTarget(manager.userId)}>
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  </Can>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {assignOpen && (
        <CloudflareAccountManagerFormDialog accountId={accountId} onClose={() => setAssignOpen(false)} />
      )}

      {removeTarget !== null && (
        <ConfirmDialog
          isOpen
          onClose={() => setRemoveTarget(null)}
          onConfirm={async () => {
            await removeManager.mutateAsync(removeTarget);
            setRemoveTarget(null);
          }}
          title={t("managers.removeConfirm.title")}
          description={t("managers.removeConfirm.description")}
          variant="destructive"
          isLoading={removeManager.isPending}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Append the export to `index.ts`**

```ts
export { CloudflareAccountDetailView } from "./ui/cloudflare-account-detail-view";
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/cloudflare-accounts/ui/cloudflare-account-manager-form-dialog.tsx frontend/src/modules/cloudflare-accounts/ui/cloudflare-account-detail-view.tsx frontend/src/modules/cloudflare-accounts/index.ts
git commit -m "feat(cloudflare-accounts): add detail view with test-connection, reveal-token, and manager CRUD"
```

---

## Task 26: App routes (list + detail) + sidebar entry

**Files:**
- Create: `frontend/src/app/[locale]/(dashboard)/admin/cloudflare-accounts/page.tsx`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/cloudflare-accounts/loading.tsx`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/cloudflare-accounts/[accountId]/page.tsx`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/cloudflare-accounts/[accountId]/loading.tsx`
- Modify: `frontend/src/app/[locale]/(dashboard)/dashboard-sidebar.tsx`
- Modify: `frontend/locales/en/common.json` (add `nav.cloudflareAccounts`)
- Modify: `frontend/locales/vi/common.json` (add `nav.cloudflareAccounts`)

**Interfaces:**
- Consumes: `fetchAuthSession`/`hasPermission`/`RequirePermission`/`NoPermission` (existing `@/modules/auth`, `@/entities/permission`), `createQueryClient` (existing `@/shared/lib/query-client`), `fetchCloudflareAccounts`/`fetchCloudflareAccount`/`cloudflareAccountsKeys` (Task 21), `CloudflareAccountsPageContent`/`CloudflareAccountDetailView` (Tasks 24/25).
- This is the last task — after it, `/admin/cloudflare-accounts` is reachable end-to-end.

- [ ] **Step 1: Write the list route `page.tsx`**

```tsx
import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchCloudflareAccounts, cloudflareAccountsKeys } from "@/entities/cloudflare-account";
import { CloudflareAccountsPageContent } from "@/modules/cloudflare-accounts";

export default async function AdminCloudflareAccountsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canView = hasPermission(session, RESOURCES.CLOUDFLARE_ACCOUNT, ACTIONS.VIEW);

  const queryClient = createQueryClient();
  if (canView) {
    await queryClient.prefetchQuery({
      queryKey: cloudflareAccountsKeys.list(),
      queryFn: () => fetchCloudflareAccounts(),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.CLOUDFLARE_ACCOUNT}
        action={ACTIONS.VIEW}
        fallback={<NoPermission />}
      >
        <CloudflareAccountsPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
```

- [ ] **Step 2: Write the list route `loading.tsx`**

```tsx
import { Skeleton } from "@/shared/ui/skeleton";

export default function Loading() {
  return (
    <div className="p-6">
      <Skeleton className="h-8 w-64 mb-2" />
      <Skeleton className="h-4 w-96 mb-6" />
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center justify-between rounded-lg border border-border p-4">
            <Skeleton className="h-4 w-48" />
            <div className="flex gap-2">
              <Skeleton className="h-8 w-8" />
              <Skeleton className="h-8 w-8" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write the detail route `[accountId]/page.tsx`**

Managers are deliberately NOT SSR-prefetched here — this mirrors the existing precedent in `admin/projects/[projectId]/page.tsx`, where the analogous nested sub-resource (`project_links`) is also fetched client-side only via its own hook, not through a server prefetch. Only the account itself is prefetched.

```tsx
import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchCloudflareAccount, cloudflareAccountsKeys } from "@/entities/cloudflare-account";
import { CloudflareAccountDetailView } from "@/modules/cloudflare-accounts";

export default async function AdminCloudflareAccountDetailPage({
  params,
}: {
  params: Promise<{ locale: string; accountId: string }>;
}) {
  const { locale, accountId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canView = hasPermission(session, RESOURCES.CLOUDFLARE_ACCOUNT, ACTIONS.VIEW);

  const queryClient = createQueryClient();
  if (canView) {
    await queryClient.prefetchQuery({
      queryKey: cloudflareAccountsKeys.detail(accountId),
      queryFn: () => fetchCloudflareAccount(accountId),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.CLOUDFLARE_ACCOUNT}
        action={ACTIONS.VIEW}
        fallback={<NoPermission />}
      >
        <CloudflareAccountDetailView accountId={accountId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
```

- [ ] **Step 4: Write the detail route `[accountId]/loading.tsx`**

```tsx
import { Skeleton } from "@/shared/ui/skeleton";

export default function Loading() {
  return (
    <div className="p-6 space-y-6">
      <Skeleton className="h-6 w-48 mb-4" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
```

- [ ] **Step 5: Add the sidebar nav entry**

In `frontend/src/app/[locale]/(dashboard)/dashboard-sidebar.tsx`: import `Cloud` alongside the other `lucide-react` icons already imported (`LayoutDashboard`, `Users`, `Shield`, `FolderKanban`, `ScrollText`, ...) — `Cloud` is distinct from environments' existing `Server` icon. Add one entry to the `navItems` array, in the same position/style as the `adminAuditLog` entry:

```tsx
  { href: ROUTES.adminCloudflareAccounts, label: t("cloudflareAccounts"), icon: Cloud, active: pathname === ROUTES.adminCloudflareAccounts, permission: { action: ACTIONS.VIEW, resource: RESOURCES.CLOUDFLARE_ACCOUNT } },
```

- [ ] **Step 6: Add the nav i18n key**

In `frontend/locales/en/common.json`'s `nav` object, add: `"cloudflareAccounts": "Cloudflare Accounts"`.

In `frontend/locales/vi/common.json`'s `nav` object, add (after `"projects": "Dự án"`): `"cloudflareAccounts": "Tài khoản Cloudflare"`.

- [ ] **Step 7: Verify end-to-end**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: both clean.

Run: `cd frontend && npm run build`
Expected: build succeeds, `/admin/cloudflare-accounts` and `/admin/cloudflare-accounts/[accountId]` both appear in the route manifest.

Manual smoke test (against the dedicated local backend/DB stack from Task 20, never the live DB): `npm run dev`, log in as a seeded admin, navigate to the sidebar's new "Cloudflare Accounts" entry, run through the master-plan Phase 3 demo script by hand.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/\[locale\]/\(dashboard\)/admin/cloudflare-accounts frontend/src/app/\[locale\]/\(dashboard\)/dashboard-sidebar.tsx frontend/locales/en/common.json frontend/locales/vi/common.json
git commit -m "feat(cloudflare-accounts): wire list/detail routes and sidebar navigation"
```

---

## Self-Review

**1. Spec coverage** — every element of the approved architecture plan's Phase 3 section is implemented by a task: migration (Task 1), constants/models (2), schemas/exceptions (3), rules incl. both structural corrections (4, 8, 10, 16), client with envelope-aware `test_connection` (5), repository/uow (6), `RbacApi.has_permission` + catalog (7), Layer-2 dependency (8), all 10 use cases incl. the previously-missing `ListVisibleCloudflareAccounts` (9-17), router with Layer-1+Layer-2 on every route (18), `public.py`/`main.py`/`.importlinter` incl. the 3-contract retrofit (19), router integration tests covering the demo script (20), and the full frontend mirror of `entities/project`+`modules/projects`+`admin/projects/[projectId]` (21-26).

**2. Placeholder scan** — no TBD/TODO markers; every step has real, complete code. The one deliberately-incomplete stub (Task 20 Step 1's `TestRevealTokenAccessLevel`) is explicitly replaced in the very next step with working code, not left dangling — flagged inline rather than silently fixed, since a bite-sized plan's steps are meant to be followed in order.

**3. Type consistency** — `AccountAccessGrant` is defined once (Task 3's `schemas.py`, specifically to avoid the dependencies.py/services circular import caught and fixed while drafting this plan) and imported identically everywhere it's used (Task 8's `dependencies.py`, Task 10's `update_account.py`, Task 18's `router.py`). `CloudflareAccountManagerRow` (repository-internal, no email/name) vs. `CloudflareAccountManagerRead` (service-layer, enriched) are kept distinct throughout — Tasks 6, 9, 14 never conflate them. `AccessLevel` values (`owner`/`editor`/`viewer`, lowercase) are consistent from the migration (Task 1) through the Zod-free TypeScript `AccessLevel` union in `modules/cloudflare-accounts/api/fetchers.ts` (Task 23) to the i18n `managers.levels.*` keys (Task 22) it looks up by exact value. `require_account_access`'s no-manager-row-vs-manage_all `None` collision (a real bug caught while writing Task 8) is fixed with an explicit guard and called out with a code comment, not silently patched.

## Verification Checklist (whole phase, after Task 26)

- [ ] `cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q` — all green.
- [ ] `cd frontend && npm run lint && npx tsc --noEmit && npm run build` — all green.
- [ ] Master-plan Phase 3 demo script, run by hand against a dedicated local test stack (never `business-chatbot-postgres`): create an account with a real/sandbox token → Test Connection succeeds → assign a VIEWER → they see the account but not the plaintext token → a user with neither `manage_all` nor a managers row sees an empty list, not a 403 → attempt to demote/remove the last OWNER → blocked on both PATCH and DELETE.
- [ ] Audit log entries exist in Mongo for every mutation, and the `reveal-token` entry's payload contains no token value (spot-check via the Phase 2 audit-log viewer UI or a direct Mongo query).
- [ ] GitNexus: `node .gitnexus/run.cjs analyze` to refresh the index post-merge; manual diff review in place of `detect_changes`/`check` (not exposed as MCP tools this session).
- [ ] `reviewing-code-against-skills` checklist, per `full-stack-dev-workflow`'s Phase 4 — including confirming `ui-ux-pro-max` was actually invoked for Tasks 24/25's UI work, not skipped.

---
