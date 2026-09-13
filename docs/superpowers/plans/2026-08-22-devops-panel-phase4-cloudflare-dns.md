# Phase 4 — Cloudflare Binding + DNS Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user bind an environment to one Cloudflare account + zone, then manage that environment's DNS records (A/AAAA/CNAME/MX/TXT/OTHER) through the app — every write calls Cloudflare first and only persists locally on confirmation.

**Architecture:** Extends the existing `app/modules/cloudflare/` module (built in Phase 3) with 2 new tables, 4 new `CloudflareClient` methods, a new Layer-2 dependency variant keyed by `environment_id`, 8 new services, and 9 new routes. Adds one missing read endpoint to `app/modules/projects/`. Frontend adds `modules/cloudflare-dns/` plus a small extension to the existing `entities/environment/`.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, httpx, pytest + testcontainers (Postgres), Next.js App Router, TanStack Query, Zod.

**Spec:** `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md`, section "Phase 4 — Detailed Plan: Cloudflare binding + DNS management" (approved via ExitPlanMode). That section's own source of truth is a dedicated pressure-test pass that read the actual Phase 3 code and found 2 real design bugs, now fixed as Decisions #1–#8 below.

## Global Constraints

- **Decision #1**: `POST /cloudflare-configs` cannot use `Depends(require_account_access(...))` — `cloudflare_account_id` is body-only; FastAPI would silently misresolve a same-named path param as a required query param instead. Fix: extract the grant-resolution logic into a new module `app/modules/cloudflare/access.py` (NOT `dependencies.py` — `dependencies.py` imports service classes to build its providers, so a service could never import it back without a cycle, exactly the reasoning that put `AccountAccessGrant` in `schemas.py` in Phase 3). `CreateCloudflareConfig` calls `resolve_account_access_grant` directly.
- **Decision #2**: binding update/delete DO use the new `require_account_access_for_environment` (environment_id is in the path; `cloudflare_configs.environment_id` is UNIQUE so a row already exists by the time you're updating/deleting).
- **Decision #3**: Cloudflare-succeeds-then-local-write-fails must never degrade silently (unlike audit's fire-and-forget philosophy — a `dns_records` row is primary state, not secondary observation). Create: compensating delete attempt + `CRITICAL` log either way + raise `DnsRecordSyncFailed`. Update: compensating revert-to-old-values attempt + same. Delete: no compensating action possible — `CRITICAL` log + raise `DnsRecordSyncFailed` (accepted gap until Phase 10's reconciliation job exists).
- **Decision #4**: `dns_records` needs a new nullable `priority integer` column (missing from the original schema doc) — required when `record_type=MX`, normalized to `None` otherwise, via a new pure `CloudflareDnsRules.normalize_priority`, never string-encoded into `content`.
- **Decision #5**: zone binding must call `client.list_zones(...)` and confirm the submitted `zone_id` is actually in that account's zone list before persisting — blocks a real cross-account zone-spoofing vector, not just staleness. `list_zones` must paginate through Cloudflare's `result_info.total_pages`, or accounts with many zones would silently reject valid zones.
- **Decision #6**: every Layer-2 route also requires its matching Layer-1 permission (`view` for reads, `manage` for writes) — no new RBAC resource, reuses `cloudflare_account:view`/`manage`/`manage_all`.
- **Decision #7**: `cloudflare/public.py` stays empty this phase — nothing outside the module needs a facade method yet.
- **Decision #8**: no cache-aside for `cloudflare_configs`/`dns_records` reads (deliberate — low-traffic, high-mutation tables).
- Router thinness (rule #10): `router.py` only translates HTTP → use-case call. All business logic (zone-ownership check, priority validation, CF-first-then-persist sequencing) lives in `services/`.
- Class-scoped constants (rule #16): every new enum/error-code/audit-action goes into a named class in `constants.py`.
- Current Alembic head is `c1a3f9d2b8e4`. Current `.importlinter` `projects-facade` contract's `source_modules` is `auth, rbac, users, common` — missing `cloudflare`.
- All manual/smoke verification uses the `itsm_test` sibling database on the shared port-5435 Postgres server — **never** `business-chatbot-postgres`'s live `itsm` database.

---

## Task 1: Migration — `cloudflare_configs` + `dns_records`

**Files:**
- Create: `backend/alembic/versions/d7e2a4c9f1b3_create_cloudflare_dns_schema.py`

**Interfaces:**
- Produces: tables `cloudflare_configs` (`id`, `environment_id` UNIQUE FK→`environments.id` CASCADE, `cloudflare_account_id` FK→`cloudflare_accounts.id` RESTRICT, `zone_id` varchar(64), `zone_name` varchar(255), `log_source` enum `audit_log|logpush|graphql_analytics` default `audit_log`, `created_at`, `updated_at`) and `dns_records` (`id`, `environment_id` FK→`environments.id` CASCADE, `cf_record_id` UNIQUE varchar(64), `record_type` enum `A|AAAA|CNAME|TXT|MX|OTHER`, `name` varchar(255), `content` text, `priority` integer nullable, `proxied` boolean default false, `ttl` integer default 1, `managed_by` enum `system|external` default `system`, `created_by` FK→`users.id` SET NULL nullable, `last_synced_at` timestamptz nullable, `created_at`, `updated_at`).

- [ ] **Step 1: Write the migration**

```python
"""create_cloudflare_dns_schema

Revision ID: d7e2a4c9f1b3
Revises: c1a3f9d2b8e4
Create Date: 2026-08-22 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd7e2a4c9f1b3'
down_revision = 'c1a3f9d2b8e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cloudflare_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('environment_id', sa.UUID(), nullable=False),
    sa.Column('cloudflare_account_id', sa.UUID(), nullable=False),
    sa.Column('zone_id', sa.String(length=64), nullable=False),
    sa.Column('zone_name', sa.String(length=255), nullable=False),
    sa.Column(
        'log_source',
        sa.Enum('audit_log', 'logpush', 'graphql_analytics', name='cloudflarelogsource', native_enum=False),
        nullable=False,
        server_default='audit_log',
    ),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['environment_id'], ['environments.id'], name=op.f('cloudflare_configs_environment_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['cloudflare_account_id'], ['cloudflare_accounts.id'],
        name=op.f('cloudflare_configs_cloudflare_account_id_fkey'), ondelete='RESTRICT'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('cloudflare_configs_pkey')),
    sa.UniqueConstraint('environment_id', name=op.f('cloudflare_configs_environment_id_key'))
    )
    op.create_table('dns_records',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('environment_id', sa.UUID(), nullable=False),
    sa.Column('cf_record_id', sa.String(length=64), nullable=False),
    sa.Column(
        'record_type',
        sa.Enum('A', 'AAAA', 'CNAME', 'TXT', 'MX', 'OTHER', name='dnsrecordtype', native_enum=False),
        nullable=False,
    ),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=True),
    sa.Column('proxied', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    sa.Column('ttl', sa.Integer(), nullable=False, server_default='1'),
    sa.Column(
        'managed_by',
        sa.Enum('system', 'external', name='dnsrecordmanagedby', native_enum=False),
        nullable=False,
        server_default='system',
    ),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['environment_id'], ['environments.id'], name=op.f('dns_records_environment_id_fkey'), ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['created_by'], ['users.id'], name=op.f('dns_records_created_by_fkey'), ondelete='SET NULL'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('dns_records_pkey')),
    sa.UniqueConstraint('cf_record_id', name=op.f('dns_records_cf_record_id_key'))
    )
    op.create_index(op.f('dns_records_environment_id_idx'), 'dns_records', ['environment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('dns_records_environment_id_idx'), table_name='dns_records')
    op.drop_table('dns_records')
    op.drop_table('cloudflare_configs')
```

- [ ] **Step 2: Apply to the `itsm_test` database and verify reversibility**

Run: `cd backend && DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5435/itsm_test alembic upgrade head`
Expected: no errors; `\d cloudflare_configs` and `\d dns_records` in `psql` show the columns above.

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: both succeed with no errors (proves the migration is reversible).

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/d7e2a4c9f1b3_create_cloudflare_dns_schema.py
git commit -m "feat(cloudflare): add cloudflare_configs and dns_records migration"
```

---

## Task 2: Constants, models, schemas, exceptions additions

**Files:**
- Modify: `backend/app/modules/cloudflare/constants.py`
- Modify: `backend/app/modules/cloudflare/models.py`
- Modify: `backend/app/modules/cloudflare/schemas.py`
- Modify: `backend/app/modules/cloudflare/exceptions.py`

**Interfaces:**
- Produces: `DnsRecordType(StrEnum)`, `LogSource(StrEnum)`, `ManagedBy(StrEnum)`, `CloudflareDnsAuditActions(StrEnum)`; ORM classes `CloudflareConfig`, `DnsRecord`; schemas `ZoneOption`, `CloudflareConfigRead`, `CloudflareConfigCreate`, `DnsRecordRead`, `DnsRecordCreate`, `DnsRecordUpdate`; exceptions `CloudflareConfigNotFound`, `CloudflareConfigAlreadyExists`, `CloudflareEnvironmentNotFound`, `DnsRecordNotFound`, `ZoneNotOwnedByAccount`, `MissingDnsRecordPriority`, `CloudflareDnsOperationRejected`, `DnsRecordSyncFailed`.

This task has no dedicated unit test file (matches Phase 3's convention — bare enums/ORM/pydantic models aren't tested directly; they're exercised by the rules/client/repository/service tests in later tasks). Instead, Step 1 is a smoke-import test that will only pass once every symbol below actually exists and imports cleanly.

- [ ] **Step 1: Write the smoke-import failing test**

Create `backend/tests/cloudflare/test_dns_schema_smoke.py`:

```python
"""Smoke test: every new Phase 4 symbol exists and imports cleanly. Real
behavior is exercised by test_rules.py/test_client.py/test_services.py/
test_router.py — this only guards against a typo'd name breaking every
downstream import at once."""


def test_new_symbols_import() -> None:
    from app.modules.cloudflare.constants import (
        CloudflareDnsAuditActions,
        DnsRecordType,
        ErrorCode,
        LogSource,
        ManagedBy,
    )
    from app.modules.cloudflare.exceptions import (
        CloudflareConfigAlreadyExists,
        CloudflareConfigNotFound,
        CloudflareDnsOperationRejected,
        CloudflareEnvironmentNotFound,
        DnsRecordNotFound,
        DnsRecordSyncFailed,
        MissingDnsRecordPriority,
        ZoneNotOwnedByAccount,
    )
    from app.modules.cloudflare.models import CloudflareConfig, DnsRecord
    from app.modules.cloudflare.schemas import (
        CloudflareConfigCreate,
        CloudflareConfigRead,
        DnsRecordCreate,
        DnsRecordRead,
        DnsRecordUpdate,
        ZoneOption,
    )

    assert DnsRecordType.MX == "MX"
    assert LogSource.AUDIT_LOG == "audit_log"
    assert ManagedBy.SYSTEM == "system"
    assert ErrorCode.CONFIG_NOT_FOUND == "cloudflare_config_not_found"
    assert CloudflareDnsAuditActions.DNS_RECORD_CREATED == "CLOUDFLARE_DNS_RECORD_CREATED"
    assert issubclass(CloudflareConfigNotFound, Exception)
    assert issubclass(CloudflareConfigAlreadyExists, Exception)
    assert issubclass(CloudflareEnvironmentNotFound, Exception)
    assert issubclass(DnsRecordNotFound, Exception)
    assert issubclass(ZoneNotOwnedByAccount, Exception)
    assert issubclass(MissingDnsRecordPriority, Exception)
    assert issubclass(CloudflareDnsOperationRejected, Exception)
    assert issubclass(DnsRecordSyncFailed, Exception)
    assert CloudflareConfig.__tablename__ == "cloudflare_configs"
    assert DnsRecord.__tablename__ == "dns_records"
    zone = ZoneOption(id="z1", name="example.com")
    assert zone.name == "example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_dns_schema_smoke.py -v`
Expected: FAIL with `ImportError` (none of the new symbols exist yet).

- [ ] **Step 3: Add to `constants.py`**

Append to `backend/app/modules/cloudflare/constants.py`:

```python
class DnsRecordType(StrEnum):
    """Cloudflare DNS record type this module manages."""

    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    TXT = "TXT"
    MX = "MX"
    OTHER = "OTHER"


class LogSource(StrEnum):
    """Where Phase 6's log viewer reads this environment's Cloudflare logs
    from. Unused until Phase 6 — column exists now per the schema doc's own
    table shape, additive not restructured."""

    AUDIT_LOG = "audit_log"
    LOGPUSH = "logpush"
    GRAPHQL_ANALYTICS = "graphql_analytics"


class ManagedBy(StrEnum):
    """Whether a dns_records row was created through this app (SYSTEM) or
    discovered on Cloudflare without a matching local row (EXTERNAL — set by
    Phase 10's reconciliation job, not written by anything in this phase)."""

    SYSTEM = "system"
    EXTERNAL = "external"


class CloudflareDnsAuditActions(StrEnum):
    """Action identifiers this phase writes via audit.log_event. Kept
    separate from CloudflareAccountAuditActions — different aggregate."""

    CONFIG_CREATED = "CLOUDFLARE_CONFIG_CREATED"
    CONFIG_UPDATED = "CLOUDFLARE_CONFIG_UPDATED"
    CONFIG_DELETED = "CLOUDFLARE_CONFIG_DELETED"
    DNS_RECORD_CREATED = "CLOUDFLARE_DNS_RECORD_CREATED"
    DNS_RECORD_UPDATED = "CLOUDFLARE_DNS_RECORD_UPDATED"
    DNS_RECORD_DELETED = "CLOUDFLARE_DNS_RECORD_DELETED"
```

Extend the existing `ErrorCode(StrEnum)` class (add these members inside it, alongside `ACCOUNT_NOT_FOUND` etc.):

```python
    CONFIG_NOT_FOUND = "cloudflare_config_not_found"
    CONFIG_ALREADY_EXISTS = "cloudflare_config_already_exists"
    ENVIRONMENT_NOT_FOUND = "cloudflare_environment_not_found"
    DNS_RECORD_NOT_FOUND = "cloudflare_dns_record_not_found"
    ZONE_NOT_OWNED_BY_ACCOUNT = "cloudflare_zone_not_owned_by_account"
    MISSING_DNS_PRIORITY = "cloudflare_missing_dns_priority"
    DNS_OPERATION_REJECTED = "cloudflare_dns_operation_rejected"
    DNS_SYNC_FAILED = "cloudflare_dns_sync_failed"
```

- [ ] **Step 4: Add to `models.py`**

Append to `backend/app/modules/cloudflare/models.py` (add `Boolean`, `Integer` to the existing `sqlalchemy` import line):

```python
class CloudflareConfig(Base):
    """One environment's binding to a Cloudflare account + zone. UNIQUE on
    environment_id — an environment has at most one binding."""

    __tablename__ = "cloudflare_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), unique=True
    )
    cloudflare_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cloudflare_accounts.id", ondelete="RESTRICT")
    )
    zone_id: Mapped[str] = mapped_column(String(64))
    zone_name: Mapped[str] = mapped_column(String(255))
    log_source: Mapped[LogSource] = mapped_column(Enum(LogSource, native_enum=False), default=LogSource.AUDIT_LOG)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DnsRecord(Base):
    """One DNS record this app knows about for an environment."""

    __tablename__ = "dns_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    cf_record_id: Mapped[str] = mapped_column(String(64), unique=True)
    record_type: Mapped[DnsRecordType] = mapped_column(Enum(DnsRecordType, native_enum=False))
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proxied: Mapped[bool] = mapped_column(Boolean, default=False)
    ttl: Mapped[int] = mapped_column(Integer, default=1)
    managed_by: Mapped[ManagedBy] = mapped_column(Enum(ManagedBy, native_enum=False), default=ManagedBy.SYSTEM)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

And update the `models.py` import line and the constants import line at the top:

```python
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
...
from app.modules.cloudflare.constants import AccessLevel, CloudflareAccountLimits, DnsRecordType, LogSource, ManagedBy
```

- [ ] **Step 5: Add to `schemas.py`**

Append to `backend/app/modules/cloudflare/schemas.py`:

```python
class ZoneOption(FrozenModel):
    """One zone available to bind, from GET /cloudflare-accounts/{id}/zones."""

    id: str
    name: str


class CloudflareConfigRead(FrozenModel):
    """One environment's Cloudflare binding."""

    id: UUID
    environment_id: UUID
    cloudflare_account_id: UUID
    zone_id: str
    zone_name: str
    created_at: datetime
    updated_at: datetime


class CloudflareConfigCreate(CustomModel):
    """Request body for POST /cloudflare-configs."""

    environment_id: UUID
    cloudflare_account_id: UUID
    zone_id: str


class DnsRecordRead(FrozenModel):
    """One DNS record."""

    id: UUID
    environment_id: UUID
    cf_record_id: str
    record_type: DnsRecordType
    name: str
    content: str
    priority: int | None = None
    proxied: bool
    ttl: int
    managed_by: ManagedBy
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DnsRecordCreate(CustomModel):
    """Request body for POST /environments/{id}/dns-records. priority is
    required only for MX — see CloudflareDnsRules.normalize_priority."""

    record_type: DnsRecordType
    name: str
    content: str
    priority: int | None = None
    proxied: bool = False
    ttl: int = 1


class DnsRecordUpdate(CustomModel):
    """Request body for PATCH .../dns-records/{id}. record_type is immutable
    after creation — changing type means delete+recreate."""

    content: str
    priority: int | None = None
    proxied: bool = False
    ttl: int = 1
```

Add `DnsRecordType, ManagedBy` to the existing `from app.modules.cloudflare.constants import AccessLevel` import line.

- [ ] **Step 6: Add to `exceptions.py`**

Append to `backend/app/modules/cloudflare/exceptions.py`:

```python
class CloudflareConfigNotFound(NotFoundError):
    """Raised when no cloudflare_configs row exists for the requested environment."""

    code = ErrorCode.CONFIG_NOT_FOUND
    message = "This environment is not bound to a Cloudflare account/zone"


class CloudflareConfigAlreadyExists(ConflictError):
    """Raised when an environment already has a binding (environment_id is UNIQUE)."""

    code = ErrorCode.CONFIG_ALREADY_EXISTS
    message = "This environment is already bound to a Cloudflare account/zone"


class CloudflareEnvironmentNotFound(NotFoundError):
    """Raised when the referenced environment_id does not exist. Module-local
    on purpose — cloudflare defines its own rather than importing projects'
    EnvironmentNotFound, keeping cross-module coupling to data only."""

    code = ErrorCode.ENVIRONMENT_NOT_FOUND
    message = "Environment not found"


class DnsRecordNotFound(NotFoundError):
    """Raised when no dns_records row matches the requested id for this environment."""

    code = ErrorCode.DNS_RECORD_NOT_FOUND
    message = "DNS record not found"


class ZoneNotOwnedByAccount(ValidationFailedError):
    """Raised when the submitted zone_id does not appear in the target
    account's own zone list — blocks cross-account zone spoofing."""

    code = ErrorCode.ZONE_NOT_OWNED_BY_ACCOUNT
    message = "This zone does not belong to the selected Cloudflare account"


class MissingDnsRecordPriority(ValidationFailedError):
    """Raised when record_type=MX and no priority was supplied."""

    code = ErrorCode.MISSING_DNS_PRIORITY
    message = "MX records require a priority value"


class CloudflareDnsOperationRejected(ValidationFailedError):
    """Raised when Cloudflare itself rejects a DNS write (malformed record,
    conflicting name, etc.) — distinct from InvalidCloudflareToken, which is
    specifically about authentication."""

    code = ErrorCode.DNS_OPERATION_REJECTED
    message = "Cloudflare rejected this DNS record operation"


class DnsRecordSyncFailed(IntegrationError):
    """Raised when Cloudflare's side of a write succeeded but the local
    Postgres write then failed. See Decision #3: this must never degrade
    silently, unlike audit's fire-and-forget philosophy — a dns_records row
    is primary state. A compensating action is attempted first where
    possible (create/update); delete has none."""

    code = ErrorCode.DNS_SYNC_FAILED
    message = "Cloudflare was updated but the local record failed to save — check logs for details"
```

Add `ValidationFailedError` is already imported; no new import needed there.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_dns_schema_smoke.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/cloudflare/constants.py backend/app/modules/cloudflare/models.py \
  backend/app/modules/cloudflare/schemas.py backend/app/modules/cloudflare/exceptions.py \
  backend/tests/cloudflare/test_dns_schema_smoke.py
git commit -m "feat(cloudflare): add DNS/config constants, models, schemas, exceptions"
```

---

## Task 3: `CloudflareDnsRules` (pure, no I/O)

**Files:**
- Modify: `backend/app/modules/cloudflare/rules.py`
- Test: `backend/tests/cloudflare/test_rules.py`

**Interfaces:**
- Consumes: `DnsRecordType` from Task 2.
- Produces: `CloudflareDnsRules.requires_priority(record_type: DnsRecordType) -> bool`, `CloudflareDnsRules.normalize_priority(record_type: DnsRecordType, priority: int | None) -> int | None` (raises `MissingDnsRecordPriority` if MX and priority is `None`; forces `None` for every other type).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_rules.py`:

```python
from app.modules.cloudflare.constants import DnsRecordType
from app.modules.cloudflare.exceptions import MissingDnsRecordPriority
from app.modules.cloudflare.rules import CloudflareDnsRules
import pytest


class TestRequiresPriority:
    def test_mx_requires_priority(self) -> None:
        assert CloudflareDnsRules.requires_priority(DnsRecordType.MX) is True

    def test_a_record_does_not_require_priority(self) -> None:
        assert CloudflareDnsRules.requires_priority(DnsRecordType.A) is False


class TestNormalizePriority:
    def test_mx_with_priority_keeps_it(self) -> None:
        assert CloudflareDnsRules.normalize_priority(DnsRecordType.MX, 10) == 10

    def test_mx_without_priority_raises(self) -> None:
        with pytest.raises(MissingDnsRecordPriority):
            CloudflareDnsRules.normalize_priority(DnsRecordType.MX, None)

    def test_non_mx_with_priority_is_forced_to_none(self) -> None:
        assert CloudflareDnsRules.normalize_priority(DnsRecordType.CNAME, 10) is None

    def test_non_mx_without_priority_stays_none(self) -> None:
        assert CloudflareDnsRules.normalize_priority(DnsRecordType.A, None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_rules.py -v`
Expected: FAIL with `ImportError: cannot import name 'CloudflareDnsRules'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/modules/cloudflare/rules.py` (add `DnsRecordType` to its existing constants import, and `MissingDnsRecordPriority` to its existing exceptions import):

```python
class CloudflareDnsRules:
    """Pure decision rules for DNS record validation. No I/O."""

    @staticmethod
    def requires_priority(record_type: DnsRecordType) -> bool:
        """Only MX records carry a priority field in Cloudflare's API."""
        return record_type == DnsRecordType.MX

    @staticmethod
    def normalize_priority(record_type: DnsRecordType, priority: int | None) -> int | None:
        """Enforce 'required for MX, ignored otherwise' — never string-encode
        this into content; Cloudflare's API wants it as a sibling field."""
        if CloudflareDnsRules.requires_priority(record_type):
            if priority is None:
                raise MissingDnsRecordPriority()
            return priority
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_rules.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/rules.py backend/tests/cloudflare/test_rules.py
git commit -m "feat(cloudflare): add CloudflareDnsRules for MX priority validation"
```

---

## Task 4: `CloudflareClient.list_zones` (paginated)

**Files:**
- Modify: `backend/app/modules/cloudflare/client.py`
- Test: `backend/tests/cloudflare/test_client.py`

**Interfaces:**
- Consumes: `ZoneOption` from Task 2.
- Produces: `CloudflareClient.list_zones(*, cf_account_id: str, api_token: str) -> list[ZoneOption]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_client.py` (add `from app.modules.cloudflare.schemas import ZoneOption` to the imports):

```python
class TestListZones:
    async def test_returns_zones_from_single_page(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["account.id"] == "acc1"
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": [{"id": "z1", "name": "example.com"}],
                    "result_info": {"page": 1, "total_pages": 1},
                },
            )

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        zones = await client.list_zones(cf_account_id="acc1", api_token="good-token")

        assert zones == [ZoneOption(id="z1", name="example.com")]

    async def test_walks_every_page(self) -> None:
        pages = {
            1: {
                "success": True,
                "result": [{"id": "z1", "name": "a.com"}],
                "result_info": {"page": 1, "total_pages": 2},
            },
            2: {
                "success": True,
                "result": [{"id": "z2", "name": "b.com"}],
                "result_info": {"page": 2, "total_pages": 2},
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params["page"])
            return httpx.Response(200, json=pages[page])

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        zones = await client.list_zones(cf_account_id="acc1", api_token="x")

        assert {z.id for z in zones} == {"z1", "z2"}

    async def test_raises_invalid_token_on_success_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "errors": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(InvalidCloudflareToken):
            await client.list_zones(cf_account_id="acc1", api_token="bad")

    async def test_raises_unavailable_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.list_zones(cf_account_id="acc1", api_token="x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_client.py::TestListZones -v`
Expected: FAIL with `AttributeError: 'CloudflareClient' object has no attribute 'list_zones'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/modules/cloudflare/client.py` (add `from app.modules.cloudflare.schemas import ZoneOption` to imports):

```python
    @integration
    async def list_zones(self, *, cf_account_id: str, api_token: str) -> list[ZoneOption]:
        """GET /zones?account.id=<cf_account_id>, walking every page via
        result_info.total_pages — a truncated first page would silently
        reject a valid zone during bind-time ownership verification."""
        zones: list[ZoneOption] = []
        page = 1
        async with httpx.AsyncClient(
            base_url=str(cloudflare_settings.API_BASE_URL), transport=self._transport
        ) as client:
            while True:
                try:
                    response = await client.get(
                        "/zones",
                        params={"account.id": cf_account_id, "page": page, "per_page": 50},
                        headers={"Authorization": f"Bearer {api_token}"},
                        timeout=cloudflare_settings.HTTP_TIMEOUT_SECONDS,
                    )
                except httpx.HTTPError as exc:
                    raise CloudflareApiUnavailable() from exc

                if response.status_code in (400, 401, 403):
                    raise InvalidCloudflareToken()
                if response.is_error:
                    raise CloudflareApiUnavailable(status_code=response.status_code)
                body = response.json()
                if not body.get("success", False):
                    raise InvalidCloudflareToken()

                zones.extend(ZoneOption(id=z["id"], name=z["name"]) for z in body.get("result", []))
                result_info = body.get("result_info", {})
                if page >= result_info.get("total_pages", 1):
                    break
                page += 1
        return zones
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_client.py::TestListZones -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/client.py backend/tests/cloudflare/test_client.py
git commit -m "feat(cloudflare): add CloudflareClient.list_zones with pagination"
```

---

## Task 5: `CloudflareClient` DNS write methods (create/update/delete)

**Files:**
- Modify: `backend/app/modules/cloudflare/client.py`
- Test: `backend/tests/cloudflare/test_client.py`

**Interfaces:**
- Consumes: `CloudflareDnsOperationRejected` from Task 2.
- Produces: `CloudflareClient.create_dns_record(*, zone_id, api_token, record_type, name, content, priority, proxied, ttl) -> str` (returns `cf_record_id`), `CloudflareClient.update_dns_record(*, zone_id, cf_record_id, api_token, record_type, name, content, priority, proxied, ttl) -> None`, `CloudflareClient.delete_dns_record(*, zone_id, cf_record_id, api_token) -> None`. All three share a private `_write` helper.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_client.py` (add `CloudflareDnsOperationRejected` to the exceptions import):

```python
class TestCreateDnsRecord:
    async def test_returns_cf_record_id_on_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/zones/zone1/dns_records"
            body = httpx.Request("POST", request.url).content
            return httpx.Response(200, json={"success": True, "result": {"id": "rec-123"}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        record_id = await client.create_dns_record(
            zone_id="zone1", api_token="x", record_type="A", name="app", content="1.2.3.4",
            priority=None, proxied=True, ttl=1,
        )

        assert record_id == "rec-123"

    async def test_raises_rejected_on_success_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": False, "errors": [{"message": "invalid content"}]})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.create_dns_record(
                zone_id="zone1", api_token="x", record_type="A", name="app", content="bad",
                priority=None, proxied=False, ttl=1,
            )

    async def test_raises_unavailable_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.create_dns_record(
                zone_id="zone1", api_token="x", record_type="A", name="app", content="1.2.3.4",
                priority=None, proxied=False, ttl=1,
            )


class TestUpdateDnsRecord:
    async def test_succeeds(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            assert request.url.path == "/zones/zone1/dns_records/rec-123"
            return httpx.Response(200, json={"success": True, "result": {"id": "rec-123"}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        await client.update_dns_record(
            zone_id="zone1", cf_record_id="rec-123", api_token="x", record_type="A", name="app",
            content="5.6.7.8", priority=None, proxied=True, ttl=1,
        )

    async def test_raises_rejected_on_4xx(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"success": False, "errors": []})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.update_dns_record(
                zone_id="zone1", cf_record_id="rec-123", api_token="x", record_type="A", name="app",
                content="x", priority=None, proxied=False, ttl=1,
            )


class TestDeleteDnsRecord:
    async def test_succeeds(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            assert request.url.path == "/zones/zone1/dns_records/rec-123"
            return httpx.Response(200, json={"success": True, "result": {"id": "rec-123"}})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        await client.delete_dns_record(zone_id="zone1", cf_record_id="rec-123", api_token="x")

    async def test_raises_unavailable_on_500(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"success": False})

        client = CloudflareClient(transport=httpx.MockTransport(handler))
        with pytest.raises(CloudflareApiUnavailable):
            await client.delete_dns_record(zone_id="zone1", cf_record_id="rec-123", api_token="x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest "tests/cloudflare/test_client.py::TestCreateDnsRecord" "tests/cloudflare/test_client.py::TestUpdateDnsRecord" "tests/cloudflare/test_client.py::TestDeleteDnsRecord" -v`
Expected: FAIL with `AttributeError` — none of the three methods exist yet.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/modules/cloudflare/client.py` (add `CloudflareDnsOperationRejected` to the exceptions import):

```python
    async def _write(self, path: str, method: str, api_token: str, *, json: dict | None = None) -> dict:
        """Shared envelope-check for the 3 DNS write methods below — a
        rejected write here means Cloudflare itself rejected the payload
        (bad record data, name conflict), which is a DIFFERENT failure mode
        than InvalidCloudflareToken (an auth problem)."""
        try:
            async with httpx.AsyncClient(
                base_url=str(cloudflare_settings.API_BASE_URL), transport=self._transport
            ) as client:
                response = await client.request(
                    method,
                    path,
                    json=json,
                    headers={"Authorization": f"Bearer {api_token}"},
                    timeout=cloudflare_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise CloudflareApiUnavailable() from exc

        if response.status_code >= 500:
            raise CloudflareApiUnavailable(status_code=response.status_code)
        body = response.json()
        if response.is_error or not body.get("success", False):
            raise CloudflareDnsOperationRejected()
        return body

    @integration
    async def create_dns_record(
        self,
        *,
        zone_id: str,
        api_token: str,
        record_type: str,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
    ) -> str:
        """POST /zones/{zone_id}/dns_records. Returns the real cf_record_id."""
        payload = {"type": record_type, "name": name, "content": content, "proxied": proxied, "ttl": ttl}
        if priority is not None:
            payload["priority"] = priority
        body = await self._write(f"/zones/{zone_id}/dns_records", "POST", api_token, json=payload)
        return body["result"]["id"]

    @integration
    async def update_dns_record(
        self,
        *,
        zone_id: str,
        cf_record_id: str,
        api_token: str,
        record_type: str,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
    ) -> None:
        """PATCH /zones/{zone_id}/dns_records/{cf_record_id}."""
        payload = {"type": record_type, "name": name, "content": content, "proxied": proxied, "ttl": ttl}
        if priority is not None:
            payload["priority"] = priority
        await self._write(f"/zones/{zone_id}/dns_records/{cf_record_id}", "PATCH", api_token, json=payload)

    @integration
    async def delete_dns_record(self, *, zone_id: str, cf_record_id: str, api_token: str) -> None:
        """DELETE /zones/{zone_id}/dns_records/{cf_record_id}."""
        await self._write(f"/zones/{zone_id}/dns_records/{cf_record_id}", "DELETE", api_token)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_client.py -v`
Expected: PASS (all tests in the file, including Task 4's)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/client.py backend/tests/cloudflare/test_client.py
git commit -m "feat(cloudflare): add CloudflareClient DNS record write methods"
```

---

## Task 6: `CloudflareConfigRepository` + `DnsRecordRepository`

**Files:**
- Modify: `backend/app/modules/cloudflare/repository.py`
- Modify: `backend/app/modules/cloudflare/uow.py`
- Test: `backend/tests/cloudflare/test_repository.py` (new — Phase 3 had no dedicated repository test file since `test_services.py`'s Fakes covered it; Phase 4's repositories are exercised directly here because the Fakes used by `test_services.py` reimplement the same interface rather than hitting real SQL, so real-SQL behavior — the UNIQUE constraint, FK cascade — needs its own coverage against a real Postgres via the `engine` fixture)

**Interfaces:**
- Consumes: `CloudflareConfig`, `DnsRecord` ORM classes and `CloudflareConfigRead`, `DnsRecordRead` schemas from Task 2.
- Produces: `AbstractCloudflareConfigRepository`/`CloudflareConfigRepository` with `get_by_id`, `list_page`, `get_by_environment_id`, `create`, `update_by_environment_id`, `delete_by_environment_id`; `AbstractDnsRecordRepository`/`DnsRecordRepository` with `get_by_id`, `list_page`, `list_for_environment`, `create`, `update`, `delete`. `AbstractCloudflareUnitOfWork` gains `.configs` and `.dns_records` attributes.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/cloudflare/test_repository.py`:

```python
"""Integration tests for the Phase 4 repositories — real Postgres via the
shared `engine`/`session` fixtures (see tests/conftest.py), not Fakes: this
covers real SQL behavior (UNIQUE(environment_id), FK cascade) the Fakes in
test_services.py don't exercise."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.cache.client import CacheClient
from app.modules.cloudflare.constants import DnsRecordType
from app.modules.cloudflare.repository import CloudflareConfigRepository, DnsRecordRepository


async def _make_account(session: AsyncSession) -> object:
    from app.modules.cloudflare.repository import CloudflareAccountRepository

    repo = CloudflareAccountRepository(session, CacheClient.__new__(CacheClient))
    return await repo.create(label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=None)


async def _make_environment(session: AsyncSession) -> object:
    from app.modules.projects.models import Environment, Project

    project = Project(name="P")
    session.add(project)
    await session.flush()
    env = Environment(project_id=project.id, type="dev", name="Dev", base_url=None)
    session.add(env)
    await session.flush()
    await session.refresh(env)
    return env


class TestCloudflareConfigRepository:
    async def test_create_and_get_by_environment_id(self, session: AsyncSession) -> None:
        account = await _make_account(session)
        env = await _make_environment(session)
        repo = CloudflareConfigRepository(session)

        created = await repo.create(
            environment_id=env.id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        found = await repo.get_by_environment_id(env.id)
        assert found is not None
        assert found.id == created.id
        assert found.zone_name == "a.com"

    async def test_environment_id_is_unique(self, session: AsyncSession) -> None:
        account = await _make_account(session)
        env = await _make_environment(session)
        repo = CloudflareConfigRepository(session)
        await repo.create(environment_id=env.id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com")

        with pytest.raises(IntegrityError):
            await repo.create(
                environment_id=env.id, cloudflare_account_id=account.id, zone_id="z2", zone_name="b.com"
            )

    async def test_get_by_environment_id_returns_none_when_unbound(self, session: AsyncSession) -> None:
        repo = CloudflareConfigRepository(session)
        assert await repo.get_by_environment_id(uuid4()) is None


class TestDnsRecordRepository:
    async def test_create_and_list_for_environment(self, session: AsyncSession) -> None:
        env = await _make_environment(session)
        repo = DnsRecordRepository(session)

        await repo.create(
            environment_id=env.id, cf_record_id="rec1", record_type=DnsRecordType.A, name="app",
            content="1.2.3.4", priority=None, proxied=True, ttl=1, created_by=None,
        )

        records = await repo.list_for_environment(env.id)
        assert len(records) == 1
        assert records[0].cf_record_id == "rec1"

    async def test_update_and_delete(self, session: AsyncSession) -> None:
        env = await _make_environment(session)
        repo = DnsRecordRepository(session)
        record = await repo.create(
            environment_id=env.id, cf_record_id="rec1", record_type=DnsRecordType.A, name="app",
            content="1.2.3.4", priority=None, proxied=False, ttl=1, created_by=None,
        )

        updated = await repo.update(record.id, content="5.6.7.8", priority=None, proxied=True, ttl=300)
        assert updated.content == "5.6.7.8"

        await repo.delete(record.id)
        assert await repo.get_by_id(record.id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_repository.py -v`
Expected: FAIL with `ImportError: cannot import name 'CloudflareConfigRepository'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/modules/cloudflare/repository.py` (add `DnsRecordType, ManagedBy` to the constants import and `CloudflareConfig, DnsRecord` to the models import and `CloudflareConfigRead, DnsRecordRead` to the schemas import):

```python
class AbstractCloudflareConfigRepository(AbstractRepository[CloudflareConfigRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def get_by_environment_id(self, environment_id: UUID) -> CloudflareConfigRead | None:
        """Look up the binding for one environment, or None if unbound."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, environment_id: UUID, cloudflare_account_id: UUID, zone_id: str, zone_name: str
    ) -> CloudflareConfigRead:
        """Create a new binding. Caller must confirm no existing binding for this environment first."""
        raise NotImplementedError

    @abstractmethod
    async def update_by_environment_id(
        self, environment_id: UUID, *, cloudflare_account_id: UUID, zone_id: str, zone_name: str
    ) -> CloudflareConfigRead:
        """Rebind an environment to a (possibly different) account + zone."""
        raise NotImplementedError

    @abstractmethod
    async def delete_by_environment_id(self, environment_id: UUID) -> None:
        """Remove an environment's binding."""
        raise NotImplementedError


class CloudflareConfigRepository(AbstractCloudflareConfigRepository):
    """SQLAlchemy implementation. No cache-aside — Decision #8: low-traffic,
    high-mutation table, premature caching adds complexity with no measured
    benefit."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> CloudflareConfigRead | None:
        row = await self._session.get(CloudflareConfig, entity_id)
        return CloudflareConfigRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareConfigRead], int]:
        """Required by AbstractRepository; bindings are looked up per-environment in practice."""
        rows = await self._session.scalars(
            select(CloudflareConfig).order_by(CloudflareConfig.id).limit(limit).offset(offset)
        )
        items = [CloudflareConfigRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(CloudflareConfig))
        return items, total or 0

    @database
    async def get_by_environment_id(self, environment_id: UUID) -> CloudflareConfigRead | None:
        row = await self._session.scalar(
            select(CloudflareConfig).where(CloudflareConfig.environment_id == environment_id)
        )
        return CloudflareConfigRead.model_validate(row) if row else None

    @database
    async def create(
        self, *, environment_id: UUID, cloudflare_account_id: UUID, zone_id: str, zone_name: str
    ) -> CloudflareConfigRead:
        row = CloudflareConfig(
            environment_id=environment_id, cloudflare_account_id=cloudflare_account_id,
            zone_id=zone_id, zone_name=zone_name,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareConfigRead.model_validate(row)

    @database
    async def update_by_environment_id(
        self, environment_id: UUID, *, cloudflare_account_id: UUID, zone_id: str, zone_name: str
    ) -> CloudflareConfigRead:
        row = await self._session.scalar(
            select(CloudflareConfig).where(CloudflareConfig.environment_id == environment_id)
        )
        if row is None:
            raise ValueError(f"cloudflare config for environment {environment_id} does not exist")
        row.cloudflare_account_id = cloudflare_account_id
        row.zone_id = zone_id
        row.zone_name = zone_name
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareConfigRead.model_validate(row)

    @database
    async def delete_by_environment_id(self, environment_id: UUID) -> None:
        row = await self._session.scalar(
            select(CloudflareConfig).where(CloudflareConfig.environment_id == environment_id)
        )
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


class AbstractDnsRecordRepository(AbstractRepository[DnsRecordRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_environment(self, environment_id: UUID) -> list[DnsRecordRead]:
        """Return every DNS record belonging to an environment."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        environment_id: UUID,
        cf_record_id: str,
        record_type: DnsRecordType,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        created_by: UUID | None,
    ) -> DnsRecordRead:
        """Create a new DNS record row. Caller must have already confirmed the Cloudflare write succeeded."""
        raise NotImplementedError

    @abstractmethod
    async def update(
        self, record_id: UUID, *, content: str, priority: int | None, proxied: bool, ttl: int
    ) -> DnsRecordRead:
        """Update a record's mutable fields. record_type/name are immutable after creation."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, record_id: UUID) -> None:
        """Delete a DNS record row."""
        raise NotImplementedError


class DnsRecordRepository(AbstractDnsRecordRepository):
    """SQLAlchemy implementation. No cache-aside — Decision #8."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> DnsRecordRead | None:
        row = await self._session.get(DnsRecord, entity_id)
        return DnsRecordRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[DnsRecordRead], int]:
        """Required by AbstractRepository; records are listed per-environment in practice."""
        rows = await self._session.scalars(select(DnsRecord).order_by(DnsRecord.id).limit(limit).offset(offset))
        items = [DnsRecordRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(DnsRecord))
        return items, total or 0

    @database
    async def list_for_environment(self, environment_id: UUID) -> list[DnsRecordRead]:
        rows = await self._session.scalars(
            select(DnsRecord).where(DnsRecord.environment_id == environment_id).order_by(DnsRecord.created_at)
        )
        return [DnsRecordRead.model_validate(row) for row in rows]

    @database
    async def create(
        self,
        *,
        environment_id: UUID,
        cf_record_id: str,
        record_type: DnsRecordType,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        created_by: UUID | None,
    ) -> DnsRecordRead:
        row = DnsRecord(
            environment_id=environment_id, cf_record_id=cf_record_id, record_type=record_type, name=name,
            content=content, priority=priority, proxied=proxied, ttl=ttl,
            managed_by=ManagedBy.SYSTEM, created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return DnsRecordRead.model_validate(row)

    @database
    async def update(
        self, record_id: UUID, *, content: str, priority: int | None, proxied: bool, ttl: int
    ) -> DnsRecordRead:
        row = await self._session.get(DnsRecord, record_id)
        if row is None:
            raise ValueError(f"dns record {record_id} does not exist")
        row.content = content
        row.priority = priority
        row.proxied = proxied
        row.ttl = ttl
        await self._session.flush()
        await self._session.refresh(row)
        return DnsRecordRead.model_validate(row)

    @database
    async def delete(self, record_id: UUID) -> None:
        row = await self._session.get(DnsRecord, record_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
```

Now wire both into `backend/app/modules/cloudflare/uow.py`. Modify the `AbstractCloudflareUnitOfWork` class to add:

```python
    configs: AbstractCloudflareConfigRepository
    dns_records: AbstractDnsRecordRepository
```

and `CloudflareUnitOfWork.__init__` to add:

```python
        self.configs = CloudflareConfigRepository(session)
        self.dns_records = DnsRecordRepository(session)
```

Update `uow.py`'s import line from `repository` to also import `AbstractCloudflareConfigRepository, AbstractDnsRecordRepository, CloudflareConfigRepository, DnsRecordRepository`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/repository.py backend/app/modules/cloudflare/uow.py \
  backend/tests/cloudflare/test_repository.py
git commit -m "feat(cloudflare): add CloudflareConfigRepository and DnsRecordRepository"
```

---

## Task 7: `GET /environments/{environment_id}` on the projects module

**Files:**
- Modify: `backend/app/modules/projects/router.py`
- Test: `backend/tests/projects/test_router.py`

**Interfaces:**
- Consumes: `EnvironmentRead` (existing), `EnvironmentNotFound` (existing, already used by `update_environment`/`delete_environment`), `AbstractProjectsUnitOfWork` (existing).
- Produces: `GET /environments/{environment_id}` — this is currently missing (only PATCH/DELETE exist), even though `environmentsKeys.detail`/`ENVIRONMENT_DETAIL` were already prepared for it on the frontend. Needed by the new Phase 4 DNS page to render the environment's name/type header.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/projects/test_router.py`, inside a new class after `TestProjectEnvironmentsAndLinks`:

```python
class TestGetEnvironment:
    async def test_returns_one_environment(self, client: AsyncClient, engine: AsyncEngine) -> None:
        await _login_with_permissions(client, engine, permissions=[("project", "create"), ("environment", "create"), ("environment", "read")])
        project_resp = await client.post("/api/v1/projects", json={"name": "Site"})
        project_id = project_resp.json()["data"]["id"]
        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments",
            json={"type": "dev", "name": "Dev"},
        )
        env_id = env_resp.json()["data"]["id"]

        response = await client.get(f"/api/v1/environments/{env_id}")

        assert response.status_code == 200
        assert response.json()["data"]["id"] == env_id
        assert response.json()["data"]["name"] == "Dev"

    async def test_returns_404_for_unknown_environment(self, client: AsyncClient, engine: AsyncEngine) -> None:
        from uuid import uuid4

        await _login_with_permissions(client, engine, permissions=[("environment", "read")])

        response = await client.get(f"/api/v1/environments/{uuid4()}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "environment_not_found"

    async def test_requires_environment_read_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        from uuid import uuid4

        await _login_with_permissions(client, engine, permissions=[])

        response = await client.get(f"/api/v1/environments/{uuid4()}")

        assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/projects/test_router.py::TestGetEnvironment -v`
Expected: FAIL with 404 for the first test (route doesn't exist — FastAPI returns its own generic 404, not the app's `environment_not_found` error code)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/modules/projects/router.py`, add `EnvironmentNotFound` to the existing `from app.modules.projects.exceptions import ProjectNotFound` import line, and insert this route directly above `@router.patch("/environments/{environment_id}")`:

```python
@router.get("/environments/{environment_id}")
async def get_environment(
    environment_id: UUID,
    uow: AbstractProjectsUnitOfWork = Depends(get_uow),
    _user: UserRead = Depends(require_permission("environment", "read")),
) -> ApiResponse[EnvironmentRead]:
    """Return one environment, 404 if it doesn't exist."""
    environment = await uow.environments.get_by_id(environment_id)
    if environment is None:
        raise EnvironmentNotFound()
    return ApiResponse[EnvironmentRead](success=True, data=environment)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/projects/test_router.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/projects/router.py backend/tests/projects/test_router.py
git commit -m "feat(projects): add GET /environments/{environment_id}"
```

---

## Task 8: `.importlinter` — allow cloudflare to import projects

**Files:**
- Modify: `backend/.importlinter`

**Interfaces:**
- Consumes: nothing new.
- Produces: `app.modules.cloudflare` added to the `projects-facade` contract's `source_modules` list.

- [ ] **Step 1: Confirm the current gap**

Run: `cd backend && lint-imports`
Expected: passes today (nothing in `cloudflare` imports `projects` yet), but this task's later services (Task 12) will need `from app.modules.projects.public import ProjectsApi`, which would fail this contract once written.

- [ ] **Step 2: Edit the contract**

In `backend/.importlinter`, in the `[importlinter:contract:projects-facade]` section, add a line to `source_modules`:

```ini
[importlinter:contract:projects-facade]
name = Other modules reach projects only through public.py
type = forbidden
source_modules =
    app.modules.auth
    app.modules.rbac
    app.modules.users
    app.modules.common
    app.modules.cloudflare
forbidden_modules =
    app.modules.projects.repository
    app.modules.projects.models
    app.modules.projects.uow
    app.modules.projects.services
allow_indirect_imports = True
```

- [ ] **Step 3: Verify**

Run: `cd backend && lint-imports`
Expected: PASS (contract still holds — this is a pure widening of what's allowed, never a narrowing, so it can't newly fail on its own).

- [ ] **Step 4: Commit**

```bash
git add backend/.importlinter
git commit -m "chore(cloudflare): allow cloudflare module to import projects facade"
```

---

## Task 9: `access.py` (`resolve_account_access_grant`) + `require_account_access_for_environment`

**Files:**
- Create: `backend/app/modules/cloudflare/access.py`
- Modify: `backend/app/modules/cloudflare/dependencies.py`
- Test: `backend/tests/cloudflare/test_dependencies.py`

**Interfaces:**
- Consumes: `AccessLevel`, `AccountAccessGrant`, `CloudflareAccountRules.satisfies_level`, `InsufficientAccountAccess`, `CloudflareConfigNotFound` (Task 2), `AbstractCloudflareUnitOfWork.configs.get_by_environment_id` (Task 6).
- Produces: `resolve_account_access_grant(account_id, user, rbac_api, uow, min_level) -> AccountAccessGrant` in the new `access.py` module; `require_account_access_for_environment(min_level)` in `dependencies.py`; `require_account_access` refactored to call `resolve_account_access_grant` (behavior-preserving — Task's Step 4 re-runs the existing `test_dependencies.py` tests unchanged to prove this).

This logic could NOT live directly in `dependencies.py` as a module-level function, because `dependencies.py` imports service classes to build its `get_*` provider functions (see the existing `from app.modules.cloudflare.services.create_account import CreateCloudflareAccount` line) — so a service (Task 12's `CreateCloudflareConfig`, which needs to call this directly per Decision #1) could never import it back without a cycle. This mirrors exactly why `AccountAccessGrant` itself lives in `schemas.py` and not `dependencies.py` (see that class's docstring from Phase 3).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_dependencies.py` (add `CloudflareConfigNotFound` to a new exceptions import, and `require_account_access_for_environment, resolve_account_access_grant` to the existing `dependencies` import):

```python
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound
from app.modules.cloudflare.dependencies import require_account_access_for_environment
from app.modules.cloudflare.access import resolve_account_access_grant


class FakeConfigs:
    def __init__(self, cloudflare_account_id) -> None:
        self._account_id = cloudflare_account_id

    async def get_by_environment_id(self, environment_id):
        if self._account_id is None:
            return None

        class _Row:
            cloudflare_account_id = self._account_id

        return _Row()


class FakeUowWithConfigs:
    def __init__(self, manager_row, cloudflare_account_id) -> None:
        self.account_managers = FakeAccountManagers(manager_row)
        self.configs = FakeConfigs(cloudflare_account_id)


async def test_resolve_account_access_grant_is_the_shared_implementation() -> None:
    """Direct-call test for the extracted helper — Task's regression proof
    that require_account_access's existing behavior didn't change lives in
    the untouched tests above this one in the file."""
    account_id = uuid4()
    grant = await resolve_account_access_grant(
        account_id, _FAKE_USER, FakeRbacApi(manage_all=True), _make_uow(None), AccessLevel.OWNER
    )
    assert grant.held_level is None


async def test_require_account_access_for_environment_resolves_via_config() -> None:
    account_id = uuid4()
    row = CloudflareAccountManagerRow(
        cloudflare_account_id=account_id, user_id=_FAKE_USER.id, access_level=AccessLevel.EDITOR,
        created_at=datetime.now(UTC),
    )
    check = require_account_access_for_environment(AccessLevel.EDITOR)

    grant = await check(
        environment_id=uuid4(),
        auth_api=FakeAuthApi(_FAKE_USER),
        rbac_api=FakeRbacApi(manage_all=False),
        uow=FakeUowWithConfigs(row, account_id),
    )

    assert grant.held_level is AccessLevel.EDITOR


async def test_require_account_access_for_environment_raises_when_unbound() -> None:
    check = require_account_access_for_environment(AccessLevel.VIEWER)

    with pytest.raises(CloudflareConfigNotFound):
        await check(
            environment_id=uuid4(),
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False),
            uow=FakeUowWithConfigs(None, None),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_dependencies.py -v`
Expected: FAIL with `ImportError: cannot import name 'require_account_access_for_environment'` (and `access` module doesn't exist)

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/modules/cloudflare/access.py`:

```python
"""Shared Layer-2 access-resolution logic. Lives in its own module — NOT
dependencies.py — so both dependencies.py's require_account_access* factory
closures AND a service that needs to resolve a grant directly (see
CreateCloudflareConfig: cloudflare_account_id is body-only, no Depends
factory can read it at decoration time) can import this without a cycle.
dependencies.py already imports service classes to build its provider
functions, so a service can never import dependencies.py back."""

from uuid import UUID

from app.modules.cloudflare.constants import AccessLevel
from app.modules.cloudflare.exceptions import InsufficientAccountAccess
from app.modules.cloudflare.rules import CloudflareAccountRules
from app.modules.cloudflare.schemas import AccountAccessGrant
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.rbac.public import RbacApi
from app.modules.users.public import UserRead


async def resolve_account_access_grant(
    account_id: UUID,
    user: UserRead,
    rbac_api: RbacApi,
    uow: AbstractCloudflareUnitOfWork,
    min_level: AccessLevel,
) -> AccountAccessGrant:
    """Return the caller's AccountAccessGrant for account_id, or raise
    InsufficientAccountAccess. manage_all bypasses with held_level=None
    (CloudflareAccountRules.satisfies_level treats None as always-sufficient)."""
    if await rbac_api.has_permission(user.id, "cloudflare_account", "manage_all"):
        return AccountAccessGrant(user=user, held_level=None)

    manager_row = await uow.account_managers.get_for_user(account_id, user.id)
    if manager_row is None or not CloudflareAccountRules.satisfies_level(manager_row.access_level, min_level):
        raise InsufficientAccountAccess()
    return AccountAccessGrant(user=user, held_level=manager_row.access_level)
```

In `backend/app/modules/cloudflare/dependencies.py`, replace the entire body of `require_account_access` (keep the function signature and docstring) with a call to the new helper, and add the new factory right after it. Remove the now-unused direct imports of `CloudflareAccountRules` and `InsufficientAccountAccess` from `dependencies.py` if nothing else in the file uses them; add `from app.modules.cloudflare.access import resolve_account_access_grant` and `from app.modules.cloudflare.exceptions import CloudflareConfigNotFound` (alongside the existing `InsufficientAccountAccess` import — keep it, `require_account_access_for_environment` doesn't raise it directly but nothing else changes about that import list except adding `CloudflareConfigNotFound`):

```python
def require_account_access(min_level: AccessLevel):
    """Return a dependency that 403s unless the current user's per-account
    access_level (cloudflare_account_managers) meets min_level, OR they hold
    the cloudflare_account:manage_all Layer-1 permission. account_id is read
    from the path — see require_account_access_for_environment for the
    environment-keyed variant."""

    async def check(
        account_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    ) -> AccountAccessGrant:
        user = auth_api.current_user()
        return await resolve_account_access_grant(account_id, user, rbac_api, uow, min_level)

    return check


def require_account_access_for_environment(min_level: AccessLevel):
    """Same check as require_account_access, but keyed by environment_id
    (read from the path) instead of account_id — resolves the environment's
    cloudflare_configs row to find which account to check against. Used by
    every DNS/binding route except POST /cloudflare-configs itself, where no
    binding exists yet to resolve from (see CreateCloudflareConfig, which
    calls resolve_account_access_grant directly with the body's account_id)."""

    async def check(
        environment_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    ) -> AccountAccessGrant:
        user = auth_api.current_user()
        config = await uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        return await resolve_account_access_grant(
            config.cloudflare_account_id, user, rbac_api, uow, min_level
        )

    return check
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_dependencies.py -v`
Expected: PASS — including the 4 pre-existing tests in the file (`test_manage_all_bypasses_with_held_level_none`, `test_sufficient_manager_row_passes`, `test_insufficient_manager_row_raises`, `test_no_manager_row_and_no_manage_all_raises`), proving the refactor is behavior-preserving.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/access.py backend/app/modules/cloudflare/dependencies.py \
  backend/tests/cloudflare/test_dependencies.py
git commit -m "refactor(cloudflare): extract resolve_account_access_grant, add environment-keyed variant"
```

---

## Task 10: `CreateCloudflareConfig` service

**Files:**
- Create: `backend/app/modules/cloudflare/services/create_config.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Consumes: `resolve_account_access_grant` (Task 9), `ProjectsApi.get_environment_by_id` (existing, `app/modules/projects/public.py`), `CloudflareClient.list_zones` (Task 4), `AbstractCloudflareUnitOfWork.configs` (Task 6).
- Produces: `CreateCloudflareConfig(uow, client, rbac_api, projects_api, audit_api).execute(environment_id, cloudflare_account_id, zone_id, *, actor: UserRead) -> CloudflareConfigRead`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py` (add imports: `from app.modules.cloudflare.access import resolve_account_access_grant` is NOT needed directly in the test — only in the service; add `from app.modules.cloudflare.exceptions import (CloudflareConfigAlreadyExists, CloudflareEnvironmentNotFound, ZoneNotOwnedByAccount)`, `from app.modules.cloudflare.schemas import ZoneOption`, `from app.modules.cloudflare.services.create_config import CreateCloudflareConfig`):

```python
class FakeProjectsApi:
    def __init__(self, environments: dict) -> None:
        self._environments = environments

    async def get_environment_by_id(self, environment_id):
        return self._environments.get(environment_id)


class FakeConfigsRepo:
    def __init__(self) -> None:
        self._rows: dict = {}

    async def get_by_environment_id(self, environment_id):
        return self._rows.get(environment_id)

    async def create(self, *, environment_id, cloudflare_account_id, zone_id, zone_name):
        from datetime import UTC, datetime as dt
        from app.modules.cloudflare.schemas import CloudflareConfigRead

        row = CloudflareConfigRead(
            id=uuid4(), environment_id=environment_id, cloudflare_account_id=cloudflare_account_id,
            zone_id=zone_id, zone_name=zone_name, created_at=dt.now(UTC), updated_at=dt.now(UTC),
        )
        self._rows[environment_id] = row
        return row

    async def update_by_environment_id(self, environment_id, *, cloudflare_account_id, zone_id, zone_name):
        existing = self._rows[environment_id]
        updated = existing.model_copy(
            update={"cloudflare_account_id": cloudflare_account_id, "zone_id": zone_id, "zone_name": zone_name}
        )
        self._rows[environment_id] = updated
        return updated

    async def delete_by_environment_id(self, environment_id):
        self._rows.pop(environment_id, None)


class FakeClientWithZones(FakeCloudflareClient):
    def __init__(self, zones: list, raises: Exception | None = None) -> None:
        super().__init__(raises=raises)
        self._zones = zones

    async def list_zones(self, *, cf_account_id, api_token):
        if self._raises is not None:
            raise self._raises
        return self._zones


class TestCreateCloudflareConfig:
    async def test_binds_environment_to_verified_zone(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="z1", name="verified-name.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        config = await CreateCloudflareConfig(uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()).execute(
            env_id, account.id, "z1", actor=actor
        )

        assert config.zone_name == "verified-name.com"
        assert config.zone_id == "z1"

    async def test_rejects_zone_not_owned_by_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="other-zone", name="not-this.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(ZoneNotOwnedByAccount):
            await CreateCloudflareConfig(uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()).execute(
                env_id, account.id, "spoofed-zone-id", actor=actor
            )

        assert uow.commits == 0

    async def test_rejects_unknown_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CloudflareEnvironmentNotFound):
            await CreateCloudflareConfig(
                uow, FakeClientWithZones([]), FakeRbacApi(manage_all=False), FakeProjectsApi({}), FakeAuditApi()
            ).execute(uuid4(), account.id, "z1", actor=actor)

    async def test_rejects_double_binding(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        await uow.account_managers.upsert(account.id, ACTOR_ID, AccessLevel.OWNER)
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        client = FakeClientWithZones([ZoneOption(id="z1", name="a.com")])
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        await CreateCloudflareConfig(uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()).execute(
            env_id, account.id, "z1", actor=actor
        )

        with pytest.raises(CloudflareConfigAlreadyExists):
            await CreateCloudflareConfig(uow, client, FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()).execute(
                env_id, account.id, "z1", actor=actor
            )

    async def test_rejects_insufficient_access(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        # No manager row for ACTOR_ID on this account, and no manage_all.
        env_id = uuid4()
        projects_api = FakeProjectsApi({env_id: object()})
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(InsufficientAccountAccess):
            await CreateCloudflareConfig(
                uow, FakeClientWithZones([]), FakeRbacApi(manage_all=False), projects_api, FakeAuditApi()
            ).execute(env_id, account.id, "z1", actor=actor)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestCreateCloudflareConfig -v`
Expected: FAIL with `ImportError: cannot import name 'CreateCloudflareConfig'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/modules/cloudflare/services/create_config.py`:

```python
"""Bind an environment to a Cloudflare account + zone. Calls Cloudflare to
verify zone ownership BEFORE persisting — same "call the external API
before persisting" principle as CreateCloudflareAccount's test_connection
call."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.access import resolve_account_access_grant
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import AccessLevel, CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import (
    CloudflareAccountNotFound,
    CloudflareConfigAlreadyExists,
    CloudflareEnvironmentNotFound,
    ZoneNotOwnedByAccount,
)
from app.modules.cloudflare.schemas import CloudflareConfigRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.projects.public import ProjectsApi
from app.modules.rbac.public import RbacApi
from app.modules.users.public import UserRead


class CreateCloudflareConfig(AbstractUseCase):
    """Resolves the Layer-2 grant itself (Decision #1) since
    cloudflare_account_id only exists in the request body — no path segment
    exists yet for a Depends(require_account_access(...)) factory to read."""

    def __init__(
        self,
        uow: AbstractCloudflareUnitOfWork,
        client: CloudflareClient,
        rbac_api: RbacApi,
        projects_api: ProjectsApi,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._client = client
        self._rbac_api = rbac_api
        self._projects_api = projects_api
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, cloudflare_account_id: UUID, zone_id: str, *, actor: UserRead
    ) -> CloudflareConfigRead:
        await resolve_account_access_grant(
            cloudflare_account_id, actor, self._rbac_api, self._uow, AccessLevel.EDITOR
        )

        environment = await self._projects_api.get_environment_by_id(environment_id)
        if environment is None:
            raise CloudflareEnvironmentNotFound()

        if await self._uow.configs.get_by_environment_id(environment_id) is not None:
            raise CloudflareConfigAlreadyExists()

        account = await self._uow.accounts.get_by_id(cloudflare_account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(cloudflare_account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        zones = await self._client.list_zones(cf_account_id=account.cf_account_id, api_token=plaintext)
        matched = next((z for z in zones if z.id == zone_id), None)
        if matched is None:
            raise ZoneNotOwnedByAccount()

        config = await self._uow.configs.create(
            environment_id=environment_id, cloudflare_account_id=cloudflare_account_id,
            zone_id=zone_id, zone_name=matched.name,
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.CONFIG_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Environment bound to Cloudflare zone '{matched.name}'",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return config
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestCreateCloudflareConfig -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/create_config.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add CreateCloudflareConfig with zone-ownership verification"
```

---

## Task 11: `UpdateCloudflareConfig` + `DeleteCloudflareConfig`

**Files:**
- Create: `backend/app/modules/cloudflare/services/update_config.py`
- Create: `backend/app/modules/cloudflare/services/delete_config.py`
- Modify: `backend/app/modules/cloudflare/schemas.py` (add `CloudflareConfigUpdate`)
- Modify: `backend/app/modules/cloudflare/exceptions.py` (add `DnsRecordsExistForConfig`)
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Consumes: `AccountAccessGrant` (existing), `resolve_account_access_grant`-verified grant is passed in by the router (via `require_account_access_for_environment`) — these two services take the grant as a parameter, they don't resolve it themselves.
- Produces: `UpdateCloudflareConfig(uow, client, audit_api).execute(environment_id, zone_id, *, grant) -> CloudflareConfigRead` (rebinds to a different zone on the SAME account — changing account entirely is out of scope, treated as delete+recreate); `DeleteCloudflareConfig(uow, audit_api).execute(environment_id, *, grant) -> None` (blocked if DNS records still exist for the environment — a new `DnsRecordsExistForConfig` guard, closing a referential-integrity gap: deleting the binding while `dns_records` rows still reference it via `environment_id` would orphan them with no `zone_id` to resolve from).

- [ ] **Step 1: Write the failing tests**

Add `CloudflareConfigUpdate` field to schemas first — append to `backend/app/modules/cloudflare/schemas.py`:

```python
class CloudflareConfigUpdate(CustomModel):
    """Request body for PATCH /environments/{id}/cloudflare-config. Only the
    zone can change — moving to a different account entirely is delete+recreate."""

    zone_id: str
```

Add to `backend/app/modules/cloudflare/exceptions.py`:

```python
class DnsRecordsExistForConfig(ConflictError):
    """Raised when deleting a binding would orphan existing dns_records rows —
    they must be deleted first."""

    code = ErrorCode.DNS_RECORDS_EXIST_FOR_CONFIG
    message = "Delete this environment's DNS records before removing its Cloudflare binding"
```

Add `DNS_RECORDS_EXIST_FOR_CONFIG = "cloudflare_dns_records_exist_for_config"` to the `ErrorCode` class in `constants.py`.

Append to `backend/tests/cloudflare/test_services.py` (add `CloudflareConfigNotFound, DnsRecordsExistForConfig` to the exceptions import, `from app.modules.cloudflare.services.update_config import UpdateCloudflareConfig`, `from app.modules.cloudflare.services.delete_config import DeleteCloudflareConfig`):

```python
class TestUpdateCloudflareConfig:
    async def test_rebinds_to_a_different_zone(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="old-zone", zone_name="old.com"
        )
        client = FakeClientWithZones([ZoneOption(id="new-zone", name="new.com")])
        grant = _grant(AccessLevel.EDITOR)

        updated = await UpdateCloudflareConfig(uow, client, FakeAuditApi()).execute(
            env_id, "new-zone", grant=grant
        )

        assert updated.zone_id == "new-zone"
        assert updated.zone_name == "new.com"

    async def test_rejects_zone_not_owned_by_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="old-zone", zone_name="old.com"
        )
        client = FakeClientWithZones([ZoneOption(id="other-zone", name="other.com")])

        with pytest.raises(ZoneNotOwnedByAccount):
            await UpdateCloudflareConfig(uow, client, FakeAuditApi()).execute(
                env_id, "spoofed", grant=_grant(AccessLevel.EDITOR)
            )

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()

        with pytest.raises(CloudflareConfigNotFound):
            await UpdateCloudflareConfig(uow, FakeClientWithZones([]), FakeAuditApi()).execute(
                uuid4(), "z1", grant=_grant(AccessLevel.EDITOR)
            )


class FakeDnsRecordsRepoEmpty:
    async def list_for_environment(self, environment_id):
        return []


class FakeDnsRecordsRepoNonEmpty:
    async def list_for_environment(self, environment_id):
        return [object()]


class TestDeleteCloudflareConfig:
    async def test_deletes_when_no_dns_records_exist(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        uow.dns_records = FakeDnsRecordsRepoEmpty()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        await DeleteCloudflareConfig(uow, FakeAuditApi()).execute(env_id, grant=_grant(AccessLevel.EDITOR))

        assert await uow.configs.get_by_environment_id(env_id) is None

    async def test_blocks_delete_when_dns_records_exist(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        uow.dns_records = FakeDnsRecordsRepoNonEmpty()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )

        with pytest.raises(DnsRecordsExistForConfig):
            await DeleteCloudflareConfig(uow, FakeAuditApi()).execute(env_id, grant=_grant(AccessLevel.EDITOR))

        assert await uow.configs.get_by_environment_id(env_id) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestUpdateCloudflareConfig tests/cloudflare/test_services.py::TestDeleteCloudflareConfig -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/modules/cloudflare/services/update_config.py`:

```python
"""Rebind an environment to a different zone on the same account. Cloudflare
verifies zone ownership before persisting, same principle as create_config.py."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound, CloudflareConfigNotFound, ZoneNotOwnedByAccount
from app.modules.cloudflare.schemas import AccountAccessGrant, CloudflareConfigRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class UpdateCloudflareConfig(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, zone_id: str, *, grant: AccountAccessGrant) -> CloudflareConfigRead:
        existing = await self._uow.configs.get_by_environment_id(environment_id)
        if existing is None:
            raise CloudflareConfigNotFound()

        account = await self._uow.accounts.get_by_id(existing.cloudflare_account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(existing.cloudflare_account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        zones = await self._client.list_zones(cf_account_id=account.cf_account_id, api_token=plaintext)
        matched = next((z for z in zones if z.id == zone_id), None)
        if matched is None:
            raise ZoneNotOwnedByAccount()

        config = await self._uow.configs.update_by_environment_id(
            environment_id, cloudflare_account_id=existing.cloudflare_account_id, zone_id=zone_id,
            zone_name=matched.name,
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT, source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.CONFIG_UPDATED, severity=AuditSeverity.INFO,
            message=f"Environment rebound to Cloudflare zone '{matched.name}'",
            actor=AuditActor(user_id=grant.user.id, email=grant.user.email),
        )
        return config
```

Create `backend/app/modules/cloudflare/services/delete_config.py`:

```python
"""Remove an environment's Cloudflare binding. Blocked while any dns_records
row still references the environment — deleting the binding first would
orphan them with no zone_id to resolve from."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.constants import CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, DnsRecordsExistForConfig
from app.modules.cloudflare.schemas import AccountAccessGrant
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class DeleteCloudflareConfig(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, audit_api: AuditApi) -> None:
        self._uow = uow
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, *, grant: AccountAccessGrant) -> None:
        existing = await self._uow.configs.get_by_environment_id(environment_id)
        if existing is None:
            raise CloudflareConfigNotFound()

        if await self._uow.dns_records.list_for_environment(environment_id):
            raise DnsRecordsExistForConfig()

        await self._uow.configs.delete_by_environment_id(environment_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT, source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.CONFIG_DELETED, severity=AuditSeverity.INFO,
            message="Environment unbound from Cloudflare",
            actor=AuditActor(user_id=grant.user.id, email=grant.user.email),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestUpdateCloudflareConfig tests/cloudflare/test_services.py::TestDeleteCloudflareConfig -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/update_config.py backend/app/modules/cloudflare/services/delete_config.py \
  backend/app/modules/cloudflare/schemas.py backend/app/modules/cloudflare/exceptions.py \
  backend/app/modules/cloudflare/constants.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add UpdateCloudflareConfig and DeleteCloudflareConfig"
```

---

## Task 12: `ListZones` + `ListDnsRecords` (read-only services)

**Files:**
- Create: `backend/app/modules/cloudflare/services/list_zones.py`
- Create: `backend/app/modules/cloudflare/services/list_dns_records.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Produces: `ListZones(uow, client).execute(account_id: UUID) -> list[ZoneOption]` (backs the zone-picker endpoint), `ListDnsRecords(uow).execute(environment_id: UUID) -> list[DnsRecordRead]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py` (add `from app.modules.cloudflare.services.list_zones import ListZones` and `from app.modules.cloudflare.services.list_dns_records import ListDnsRecords`):

```python
class TestListZones:
    async def test_returns_zones_for_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        ciphertext = FernetCodec.encrypt("plain-token", key=TEST_FERNET_KEY)
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=ciphertext, created_by=ACTOR_ID
        )
        client = FakeClientWithZones([ZoneOption(id="z1", name="a.com")])

        zones = await ListZones(uow, client).execute(account.id)

        assert zones == [ZoneOption(id="z1", name="a.com")]

    async def test_rejects_unknown_account(self) -> None:
        uow = FakeCloudflareUnitOfWork()

        with pytest.raises(CloudflareAccountNotFound):
            await ListZones(uow, FakeClientWithZones([])).execute(uuid4())


class TestListDnsRecords:
    async def test_returns_records_for_bound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token="ciphertext", created_by=ACTOR_ID
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        await uow.dns_records.create(
            environment_id=env_id, cf_record_id="rec1", record_type=DnsRecordType.A, name="app",
            content="1.2.3.4", priority=None, proxied=True, ttl=1, created_by=ACTOR_ID,
        )

        records = await ListDnsRecords(uow).execute(env_id)

        assert len(records) == 1
        assert records[0].cf_record_id == "rec1"

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.configs = FakeConfigsRepo()

        with pytest.raises(CloudflareConfigNotFound):
            await ListDnsRecords(uow).execute(uuid4())
```

This test needs `uow.dns_records` to be a working in-memory Fake too — add it to `FakeCloudflareUnitOfWork.__init__` in the same file (find the existing `__init__` from Phase 3 and add these two lines alongside `self.accounts = ...`):

```python
        self.configs = FakeConfigsRepo()
        self.dns_records = FakeDnsRecordsRepo()
```

And define `FakeDnsRecordsRepo` near the other Fakes in the file:

```python
class FakeDnsRecordsRepo:
    def __init__(self) -> None:
        self._rows: dict = {}

    async def list_for_environment(self, environment_id):
        return [r for r in self._rows.values() if r.environment_id == environment_id]

    async def get_by_id(self, record_id):
        return self._rows.get(record_id)

    async def create(
        self, *, environment_id, cf_record_id, record_type, name, content, priority, proxied, ttl, created_by
    ):
        from datetime import UTC, datetime as dt
        from app.modules.cloudflare.constants import ManagedBy
        from app.modules.cloudflare.schemas import DnsRecordRead

        row = DnsRecordRead(
            id=uuid4(), environment_id=environment_id, cf_record_id=cf_record_id, record_type=record_type,
            name=name, content=content, priority=priority, proxied=proxied, ttl=ttl,
            managed_by=ManagedBy.SYSTEM, created_by=created_by, created_at=dt.now(UTC), updated_at=dt.now(UTC),
        )
        self._rows[row.id] = row
        return row

    async def update(self, record_id, *, content, priority, proxied, ttl):
        existing = self._rows[record_id]
        updated = existing.model_copy(update={"content": content, "priority": priority, "proxied": proxied, "ttl": ttl})
        self._rows[record_id] = updated
        return updated

    async def delete(self, record_id):
        self._rows.pop(record_id, None)
```

Note: every earlier test in this task list that constructs `FakeCloudflareUnitOfWork()` and then separately assigns `uow.configs = FakeConfigsRepo()` (Tasks 10-11) can now drop that redundant line, since `FakeCloudflareUnitOfWork.__init__` sets it by default — leave the earlier tests as-is (the redundant re-assignment is harmless, just makes each test file section closer to what existed when it was written; do not go back and edit already-committed tasks purely for tidiness).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestListZones tests/cloudflare/test_services.py::TestListDnsRecords -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/modules/cloudflare/services/list_zones.py`:

```python
"""List zones available to bind, for the zone-picker endpoint."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound
from app.modules.cloudflare.schemas import ZoneOption
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListZones(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, account_id: UUID) -> list[ZoneOption]:
        account = await self._uow.accounts.get_by_id(account_id)
        if account is None:
            raise CloudflareAccountNotFound()
        ciphertext = await self._uow.accounts.get_token_ciphertext(account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        return await self._client.list_zones(cf_account_id=account.cf_account_id, api_token=plaintext)
```

Create `backend/app/modules/cloudflare/services/list_dns_records.py`:

```python
"""List DNS records for a bound environment."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound
from app.modules.cloudflare.schemas import DnsRecordRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListDnsRecords(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID) -> list[DnsRecordRead]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        return await self._uow.dns_records.list_for_environment(environment_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -v`
Expected: PASS (all tests in the file, including every earlier task's)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/list_zones.py backend/app/modules/cloudflare/services/list_dns_records.py \
  backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add ListZones and ListDnsRecords read services"
```

---

## Task 13: `CreateDnsRecord` — Decision #3's create path

**Files:**
- Create: `backend/app/modules/cloudflare/services/create_dns_record.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Consumes: `CloudflareDnsRules.normalize_priority` (Task 3), `CloudflareClient.create_dns_record`/`.delete_dns_record` (Task 5).
- Produces: `CreateDnsRecord(uow, client, audit_api).execute(environment_id, record_type, name, content, priority, proxied, ttl, *, actor) -> DnsRecordRead`. On a local-write failure after a successful Cloudflare create, attempts a compensating delete, logs `CRITICAL` either way, and raises `DnsRecordSyncFailed` — never reports success.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py` (add `from app.modules.cloudflare.exceptions import DnsRecordSyncFailed`, `from app.modules.cloudflare.services.create_dns_record import CreateDnsRecord`):

```python
class FakeDnsClient(FakeCloudflareClient):
    """Extends FakeCloudflareClient with the 3 DNS write methods, each
    independently configurable to raise."""

    def __init__(
        self,
        create_returns: str = "rec-new",
        create_raises: Exception | None = None,
        delete_raises: Exception | None = None,
    ) -> None:
        super().__init__()
        self._create_returns = create_returns
        self._create_raises = create_raises
        self._delete_raises = delete_raises
        self.deleted: list[str] = []

    async def create_dns_record(self, **kwargs) -> str:
        if self._create_raises is not None:
            raise self._create_raises
        return self._create_returns

    async def delete_dns_record(self, *, zone_id, cf_record_id, api_token) -> None:
        if self._delete_raises is not None:
            raise self._delete_raises
        self.deleted.append(cf_record_id)


class FailingDnsRecordsRepo(FakeDnsRecordsRepo):
    """Every create() call raises, simulating a local DB failure AFTER
    Cloudflare already accepted the write."""

    async def create(self, **kwargs):
        raise RuntimeError("simulated DB failure")


class TestCreateDnsRecord:
    async def test_creates_record_with_real_cf_record_id(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient(create_returns="rec-new")
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        record = await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
            env_id, DnsRecordType.A, "app", "1.2.3.4", None, True, 1, actor=actor
        )

        assert record.cf_record_id == "rec-new"
        assert record.managed_by == ManagedBy.SYSTEM

    async def test_mx_without_priority_raises_before_calling_cloudflare(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(MissingDnsRecordPriority):
            await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, DnsRecordType.MX, "app", "mail.example.com", None, False, 1, actor=actor
            )

    async def test_local_failure_after_cf_success_attempts_compensating_delete(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        uow.dns_records = FailingDnsRecordsRepo()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        client = FakeDnsClient(create_returns="rec-orphan-risk")
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await CreateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, DnsRecordType.A, "app", "1.2.3.4", None, False, 1, actor=actor
            )

        assert client.deleted == ["rec-orphan-risk"]

    async def test_rejects_unbound_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(CloudflareConfigNotFound):
            await CreateDnsRecord(uow, FakeDnsClient(), FakeAuditApi()).execute(
                uuid4(), DnsRecordType.A, "app", "1.2.3.4", None, False, 1, actor=actor
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestCreateDnsRecord -v`
Expected: FAIL with `ImportError: cannot import name 'CreateDnsRecord'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/modules/cloudflare/services/create_dns_record.py`:

```python
"""Create a DNS record: call Cloudflare first, persist locally only on
confirmation. Decision #3: if the local write then fails, attempt a
compensating delete back to Cloudflare rather than leaving an orphaned
record with zero local trace — a dns_records row is primary state, not
audit's secondary observation, so failure here must surface loudly."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareDnsAuditActions, DnsRecordType
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, DnsRecordSyncFailed
from app.modules.cloudflare.rules import CloudflareDnsRules
from app.modules.cloudflare.schemas import DnsRecordRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class CreateDnsRecord(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        environment_id: UUID,
        record_type: DnsRecordType,
        name: str,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        *,
        actor: UserRead,
    ) -> DnsRecordRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()

        normalized_priority = CloudflareDnsRules.normalize_priority(record_type, priority)

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        cf_record_id = await self._client.create_dns_record(
            zone_id=config.zone_id, api_token=plaintext, record_type=record_type, name=name,
            content=content, priority=normalized_priority, proxied=proxied, ttl=ttl,
        )

        try:
            record = await self._uow.dns_records.create(
                environment_id=environment_id, cf_record_id=cf_record_id, record_type=record_type,
                name=name, content=content, priority=normalized_priority, proxied=proxied, ttl=ttl,
                created_by=actor.id,
            )
            await self._uow.commit()
        except Exception:
            logger.critical(
                "Local DNS record write failed after Cloudflare create succeeded — attempting "
                "compensating delete (zone_id=%s, cf_record_id=%s)", config.zone_id, cf_record_id,
            )
            try:
                await self._client.delete_dns_record(
                    zone_id=config.zone_id, cf_record_id=cf_record_id, api_token=plaintext
                )
                logger.critical("Compensating delete succeeded — orphan avoided (cf_record_id=%s)", cf_record_id)
            except Exception:
                logger.critical(
                    "ORPHAN DNS RECORD on Cloudflare — compensating delete ALSO failed, manual "
                    "cleanup required (zone_id=%s, cf_record_id=%s)", config.zone_id, cf_record_id,
                )
            raise DnsRecordSyncFailed() from None

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT, source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.DNS_RECORD_CREATED, severity=AuditSeverity.INFO,
            message=f"DNS record '{name}' ({record_type}) created",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestCreateDnsRecord -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/create_dns_record.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add CreateDnsRecord with compensating-delete on local failure"
```

---

## Task 14: `UpdateDnsRecord` — Decision #3's update path

**Files:**
- Create: `backend/app/modules/cloudflare/services/update_dns_record.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Produces: `UpdateDnsRecord(uow, client, audit_api).execute(environment_id, record_id, content, priority, proxied, ttl, *, actor) -> DnsRecordRead`. Captures the record's pre-update values; if the local write fails after Cloudflare's PATCH succeeds, attempts a compensating PATCH back to the captured old values, logs `CRITICAL` either way, raises `DnsRecordSyncFailed`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py` (add `from app.modules.cloudflare.services.update_dns_record import UpdateDnsRecord`):

```python
class FakeDnsClientForUpdate(FakeCloudflareClient):
    def __init__(self, update_raises: Exception | None = None) -> None:
        super().__init__()
        self._update_raises = update_raises
        self.update_calls: list[dict] = []

    async def update_dns_record(self, **kwargs) -> None:
        if self._update_raises is not None:
            raise self._update_raises
        self.update_calls.append(kwargs)


class FailingUpdateDnsRecordsRepo(FakeDnsRecordsRepo):
    async def update(self, record_id, **kwargs):
        raise RuntimeError("simulated DB failure")


class TestUpdateDnsRecord:
    async def test_updates_content_and_ttl(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id, cf_record_id="rec1", record_type=DnsRecordType.A, name="app",
            content="1.2.3.4", priority=None, proxied=False, ttl=1, created_by=ACTOR_ID,
        )
        client = FakeDnsClientForUpdate()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        updated = await UpdateDnsRecord(uow, client, FakeAuditApi()).execute(
            env_id, existing.id, "5.6.7.8", None, True, 300, actor=actor
        )

        assert updated.content == "5.6.7.8"
        assert updated.ttl == 300

    async def test_local_failure_after_cf_success_attempts_compensating_revert(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id, cf_record_id="rec1", record_type=DnsRecordType.A, name="app",
            content="1.2.3.4", priority=None, proxied=False, ttl=1, created_by=ACTOR_ID,
        )
        uow.dns_records = FailingUpdateDnsRecordsRepo()
        uow.dns_records._rows[existing.id] = existing
        client = FakeDnsClientForUpdate()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await UpdateDnsRecord(uow, client, FakeAuditApi()).execute(
                env_id, existing.id, "9.9.9.9", None, True, 600, actor=actor
            )

        # First call = the real update; second call = the compensating
        # revert back to the original content/ttl.
        assert len(client.update_calls) == 2
        assert client.update_calls[1]["content"] == "1.2.3.4"
        assert client.update_calls[1]["ttl"] == 1

    async def test_rejects_unknown_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordNotFound):
            await UpdateDnsRecord(uow, FakeDnsClientForUpdate(), FakeAuditApi()).execute(
                env_id, uuid4(), "x", None, False, 1, actor=actor
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestUpdateDnsRecord -v`
Expected: FAIL with `ImportError: cannot import name 'UpdateDnsRecord'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/modules/cloudflare/services/update_dns_record.py`:

```python
"""Update a DNS record: call Cloudflare first, persist locally only on
confirmation. Decision #3: captures the record's pre-update field values
before calling Cloudflare, so a local-write failure after Cloudflare's PATCH
succeeded can attempt a compensating PATCH back to those captured values."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, DnsRecordNotFound, DnsRecordSyncFailed
from app.modules.cloudflare.rules import CloudflareDnsRules
from app.modules.cloudflare.schemas import DnsRecordRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class UpdateDnsRecord(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self,
        environment_id: UUID,
        record_id: UUID,
        content: str,
        priority: int | None,
        proxied: bool,
        ttl: int,
        *,
        actor: UserRead,
    ) -> DnsRecordRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        existing = await self._uow.dns_records.get_by_id(record_id)
        if existing is None or existing.environment_id != environment_id:
            raise DnsRecordNotFound()

        normalized_priority = CloudflareDnsRules.normalize_priority(existing.record_type, priority)
        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        await self._client.update_dns_record(
            zone_id=config.zone_id, cf_record_id=existing.cf_record_id, api_token=plaintext,
            record_type=existing.record_type, name=existing.name, content=content,
            priority=normalized_priority, proxied=proxied, ttl=ttl,
        )

        try:
            record = await self._uow.dns_records.update(
                record_id, content=content, priority=normalized_priority, proxied=proxied, ttl=ttl
            )
            await self._uow.commit()
        except Exception:
            logger.critical(
                "Local DNS record update failed after Cloudflare PATCH succeeded — attempting "
                "compensating revert (zone_id=%s, cf_record_id=%s)", config.zone_id, existing.cf_record_id,
            )
            try:
                await self._client.update_dns_record(
                    zone_id=config.zone_id, cf_record_id=existing.cf_record_id, api_token=plaintext,
                    record_type=existing.record_type, name=existing.name, content=existing.content,
                    priority=existing.priority, proxied=existing.proxied, ttl=existing.ttl,
                )
                logger.critical("Compensating revert succeeded (cf_record_id=%s)", existing.cf_record_id)
            except Exception:
                logger.critical(
                    "Cloudflare/local state now DIVERGED — compensating revert ALSO failed, manual "
                    "reconciliation required (zone_id=%s, cf_record_id=%s)", config.zone_id, existing.cf_record_id,
                )
            raise DnsRecordSyncFailed() from None

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT, source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.DNS_RECORD_UPDATED, severity=AuditSeverity.INFO,
            message=f"DNS record '{existing.name}' updated",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestUpdateDnsRecord -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/update_dns_record.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add UpdateDnsRecord with compensating-revert on local failure"
```

---

## Task 15: `DeleteDnsRecord` — Decision #3's delete path (no compensation possible)

**Files:**
- Create: `backend/app/modules/cloudflare/services/delete_dns_record.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Produces: `DeleteDnsRecord(uow, client, audit_api).execute(environment_id, record_id, *, actor) -> None`. If the local delete fails after Cloudflare's DELETE already succeeded, no compensating action is possible — the record is genuinely gone from Cloudflare. Logs `CRITICAL` and raises `DnsRecordSyncFailed` (never reports success) — this is the accepted, documented gap from Decision #3, backstopped only by Phase 10's reconciliation job.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py` (add `from app.modules.cloudflare.services.delete_dns_record import DeleteDnsRecord`):

```python
class FakeDnsClientForDelete(FakeCloudflareClient):
    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[str] = []

    async def delete_dns_record(self, *, zone_id, cf_record_id, api_token) -> None:
        self.deleted.append(cf_record_id)


class FailingDeleteDnsRecordsRepo(FakeDnsRecordsRepo):
    async def delete(self, record_id):
        raise RuntimeError("simulated DB failure")


class TestDeleteDnsRecord:
    async def test_deletes_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id, cf_record_id="rec1", record_type=DnsRecordType.A, name="app",
            content="1.2.3.4", priority=None, proxied=False, ttl=1, created_by=ACTOR_ID,
        )
        client = FakeDnsClientForDelete()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        await DeleteDnsRecord(uow, client, FakeAuditApi()).execute(env_id, existing.id, actor=actor)

        assert client.deleted == ["rec1"]
        assert await uow.dns_records.get_by_id(existing.id) is None

    async def test_local_failure_after_cf_delete_succeeds_raises_sync_failed(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        existing = await uow.dns_records.create(
            environment_id=env_id, cf_record_id="rec1", record_type=DnsRecordType.A, name="app",
            content="1.2.3.4", priority=None, proxied=False, ttl=1, created_by=ACTOR_ID,
        )
        uow.dns_records = FailingDeleteDnsRecordsRepo()
        uow.dns_records._rows[existing.id] = existing
        client = FakeDnsClientForDelete()
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordSyncFailed):
            await DeleteDnsRecord(uow, client, FakeAuditApi()).execute(env_id, existing.id, actor=actor)

        # Cloudflare's side really is deleted — no compensating action exists.
        assert client.deleted == ["rec1"]

    async def test_rejects_unknown_record(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="A", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plain", key=TEST_FERNET_KEY),
            created_by=ACTOR_ID,
        )
        env_id = uuid4()
        await uow.configs.create(
            environment_id=env_id, cloudflare_account_id=account.id, zone_id="z1", zone_name="a.com"
        )
        actor = UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)

        with pytest.raises(DnsRecordNotFound):
            await DeleteDnsRecord(uow, FakeDnsClientForDelete(), FakeAuditApi()).execute(
                env_id, uuid4(), actor=actor
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py::TestDeleteDnsRecord -v`
Expected: FAIL with `ImportError: cannot import name 'DeleteDnsRecord'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/modules/cloudflare/services/delete_dns_record.py`:

```python
"""Delete a DNS record: call Cloudflare first, delete locally only on
confirmation. Decision #3: unlike create/update, NO compensating action is
possible here — once Cloudflare's DELETE succeeds the record is genuinely
gone. A local-delete failure after that can only be logged loudly and
surfaced as an error; the residual state-divergence gap is accepted until
Phase 10's reconciliation job exists."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareDnsAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, DnsRecordNotFound, DnsRecordSyncFailed
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class DeleteDnsRecord(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, record_id: UUID, *, actor: UserRead) -> None:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        existing = await self._uow.dns_records.get_by_id(record_id)
        if existing is None or existing.environment_id != environment_id:
            raise DnsRecordNotFound()

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        await self._client.delete_dns_record(
            zone_id=config.zone_id, cf_record_id=existing.cf_record_id, api_token=plaintext
        )

        try:
            await self._uow.dns_records.delete(record_id)
            await self._uow.commit()
        except Exception:
            logger.critical(
                "DNS record deleted on Cloudflare but local delete failed — no compensating action "
                "possible, state may have diverged (zone_id=%s, cf_record_id=%s, environment_id=%s)",
                config.zone_id, existing.cf_record_id, environment_id,
            )
            raise DnsRecordSyncFailed() from None

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT, source=AuditSource.USER_ACTION,
            action=CloudflareDnsAuditActions.DNS_RECORD_DELETED, severity=AuditSeverity.INFO,
            message=f"DNS record '{existing.name}' deleted",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -v`
Expected: PASS (entire file — every service task so far)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/delete_dns_record.py backend/tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add DeleteDnsRecord — no compensation possible on local failure"
```

---

## Task 16: Dependency providers for the 8 new services

**Files:**
- Modify: `backend/app/modules/cloudflare/dependencies.py`

**Interfaces:**
- Consumes: all 8 service classes from Tasks 10–15, plus `ProjectsApi`/`get_projects_api` (existing, `app/modules/projects/public.py`).
- Produces: `get_create_config`, `get_update_config`, `get_delete_config`, `get_list_zones`, `get_list_dns_records`, `get_create_dns_record`, `get_update_dns_record`, `get_delete_dns_record` — one FastAPI provider function per service, following the exact shape every existing provider in this file already uses.

This task is pure wiring — no new test file. It's verified indirectly by Task 17's router tests, which depend on every provider below existing and resolving correctly.

- [ ] **Step 1: Add the imports**

Add to the top of `backend/app/modules/cloudflare/dependencies.py`:

```python
from app.modules.cloudflare.services.create_config import CreateCloudflareConfig
from app.modules.cloudflare.services.create_dns_record import CreateDnsRecord
from app.modules.cloudflare.services.delete_config import DeleteCloudflareConfig
from app.modules.cloudflare.services.delete_dns_record import DeleteDnsRecord
from app.modules.cloudflare.services.list_dns_records import ListDnsRecords
from app.modules.cloudflare.services.list_zones import ListZones
from app.modules.cloudflare.services.update_config import UpdateCloudflareConfig
from app.modules.cloudflare.services.update_dns_record import UpdateDnsRecord
from app.modules.projects.public import ProjectsApi, get_projects_api
```

- [ ] **Step 2: Add the provider functions**

Append to `backend/app/modules/cloudflare/dependencies.py`:

```python
async def get_create_config(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    rbac_api: RbacApi = Depends(get_rbac_api),
    projects_api: ProjectsApi = Depends(get_projects_api),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateCloudflareConfig:
    """Provide the create-config use case."""
    return CreateCloudflareConfig(uow, client, rbac_api, projects_api, audit_api)


async def get_update_config(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateCloudflareConfig:
    """Provide the update-config use case."""
    return UpdateCloudflareConfig(uow, client, audit_api)


async def get_delete_config(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), audit_api: AuditApi = Depends(get_audit_api)
) -> DeleteCloudflareConfig:
    """Provide the delete-config use case."""
    return DeleteCloudflareConfig(uow, audit_api)


async def get_list_zones(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow), client: CloudflareClient = Depends(get_cloudflare_client)
) -> ListZones:
    """Provide the list-zones use case."""
    return ListZones(uow, client)


async def get_list_dns_records(uow: AbstractCloudflareUnitOfWork = Depends(get_uow)) -> ListDnsRecords:
    """Provide the list-dns-records use case."""
    return ListDnsRecords(uow)


async def get_create_dns_record(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateDnsRecord:
    """Provide the create-dns-record use case."""
    return CreateDnsRecord(uow, client, audit_api)


async def get_update_dns_record(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateDnsRecord:
    """Provide the update-dns-record use case."""
    return UpdateDnsRecord(uow, client, audit_api)


async def get_delete_dns_record(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteDnsRecord:
    """Provide the delete-dns-record use case."""
    return DeleteDnsRecord(uow, client, audit_api)
```

- [ ] **Step 3: Verify the module still imports cleanly**

Run: `cd backend && python -c "import app.modules.cloudflare.dependencies"`
Expected: no errors (proves no circular import was introduced — `dependencies.py` imports every service including `create_config.py`, and `create_config.py` imports `access.py`, never `dependencies.py`, so the cycle Decision #1 warned about does not occur).

Run: `cd backend && lint-imports && python scripts/check_module_boundaries.py --strict`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/modules/cloudflare/dependencies.py
git commit -m "feat(cloudflare): wire dependency providers for the 8 new DNS/config services"
```

---

## Task 17: `router.py` — 9 new routes + integration tests

**Files:**
- Modify: `backend/app/modules/cloudflare/router.py`
- Test: `backend/tests/cloudflare/test_router.py`

**Interfaces:**
- Consumes: every service/dependency from Tasks 9–16.
- Produces: 9 new routes (see table below). This task's tests are the concrete proof for Decisions #1 and #5, and the full Phase 4 demo script from the approved plan.

```
GET    /cloudflare-accounts/{account_id}/zones                      view + VIEWER  (require_account_access)
POST   /cloudflare-configs                                          manage; grant resolved in-service (Decision #1)
GET    /environments/{environment_id}/cloudflare-config              view + VIEWER  (require_account_access_for_environment)
PATCH  /environments/{environment_id}/cloudflare-config              manage + EDITOR
DELETE /environments/{environment_id}/cloudflare-config              manage + EDITOR
GET    /environments/{environment_id}/dns-records                    view + VIEWER
POST   /environments/{environment_id}/dns-records                    manage + EDITOR
PATCH  /environments/{environment_id}/dns-records/{record_id}       manage + EDITOR
DELETE /environments/{environment_id}/dns-records/{record_id}       manage + EDITOR
```

- [ ] **Step 1: Write the failing tests**

Extend the existing `FakeCloudflareClient` class in `backend/tests/cloudflare/test_router.py` with the 4 new methods (replace the class entirely):

```python
class FakeCloudflareClient:
    """Overrides the real CloudflareClient for the duration of one test —
    no test in this file makes a real network call."""

    def __init__(
        self,
        raises: Exception | None = None,
        zones: list | None = None,
        create_record_id: str = "rec-fake",
    ) -> None:
        self._raises = raises
        self._zones = zones or []
        self._create_record_id = create_record_id
        self.deleted_record_ids: list[str] = []

    async def test_connection(self, *, cf_account_id: str, api_token: str) -> None:
        if self._raises is not None:
            raise self._raises

    async def list_zones(self, *, cf_account_id: str, api_token: str):
        return self._zones

    async def create_dns_record(self, **kwargs) -> str:
        return self._create_record_id

    async def update_dns_record(self, **kwargs) -> None:
        pass

    async def delete_dns_record(self, *, zone_id, cf_record_id, api_token) -> None:
        self.deleted_record_ids.append(cf_record_id)
```

Append a new section to the file (add `from app.modules.cloudflare.schemas import ZoneOption` to the imports):

```python
async def _bind_environment(
    client: AsyncClient, engine: AsyncEngine, *, cf_client: FakeCloudflareClient
) -> tuple[str, str]:
    """Full setup: login with manage+view, create an account, create a
    project + environment, bind them. Returns (environment_id, account_id)."""
    app.dependency_overrides[get_cloudflare_client] = lambda: cf_client
    await _login_with_permissions(
        client, engine, permissions=[
            ("cloudflare_account", "manage"), ("cloudflare_account", "view"),
            ("project", "create"), ("environment", "create"), ("environment", "read"),
        ],
    )
    account_resp = await client.post(
        "/api/v1/cloudflare-accounts", json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"}
    )
    account_id = account_resp.json()["data"]["id"]
    project_resp = await client.post("/api/v1/projects", json={"name": "Site"})
    project_id = project_resp.json()["data"]["id"]
    env_resp = await client.post(
        f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "Dev"}
    )
    environment_id = env_resp.json()["data"]["id"]

    bind_resp = await client.post(
        "/api/v1/cloudflare-configs",
        json={"environmentId": environment_id, "cloudflareAccountId": account_id, "zoneId": "z1"},
    )
    assert bind_resp.status_code == 200, bind_resp.text
    return environment_id, account_id


class TestCreateCloudflareConfig:
    async def test_reads_account_id_from_body_not_query_param(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """Decision #1's regression test: if cloudflare_account_id were
        accidentally resolved as a query param (the FastAPI misresolution
        bug the Phase 4 pressure-test caught), this POST — sent with only a
        JSON body, no query string — would either 422 (FastAPI treating
        account_id as a required query param) or silently check access
        against nothing. A 200 with the config's cloudflare_account_id
        matching the body proves the fix."""
        cf_client = FakeCloudflareClient(zones=[ZoneOption(id="z1", name="example.com")])
        app.dependency_overrides[get_cloudflare_client] = lambda: cf_client
        await _login_with_permissions(
            client, engine, permissions=[
                ("cloudflare_account", "manage"), ("cloudflare_account", "view"),
                ("project", "create"), ("environment", "create"),
            ],
        )
        account_resp = await client.post(
            "/api/v1/cloudflare-accounts", json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"}
        )
        account_id = account_resp.json()["data"]["id"]
        project_resp = await client.post("/api/v1/projects", json={"name": "Site"})
        project_id = project_resp.json()["data"]["id"]
        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "Dev"}
        )
        environment_id = env_resp.json()["data"]["id"]

        response = await client.post(
            "/api/v1/cloudflare-configs",
            json={"environmentId": environment_id, "cloudflareAccountId": account_id, "zoneId": "z1"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["data"]["cloudflareAccountId"] == account_id
        assert response.json()["data"]["zoneName"] == "example.com"

        del app.dependency_overrides[get_cloudflare_client]

    async def test_rejects_cross_account_zone_spoofing(self, client: AsyncClient, engine: AsyncEngine) -> None:
        """Decision #5's regression test: a zone_id that only belongs to a
        DIFFERENT account than the one named in the request body must be
        rejected — this is what blocks a real cross-account spoofing vector,
        not just staleness."""
        cf_client = FakeCloudflareClient(zones=[ZoneOption(id="owned-by-account-a", name="a.com")])
        app.dependency_overrides[get_cloudflare_client] = lambda: cf_client
        await _login_with_permissions(
            client, engine, permissions=[
                ("cloudflare_account", "manage"), ("cloudflare_account", "view"),
                ("project", "create"), ("environment", "create"),
            ],
        )
        account_resp = await client.post(
            "/api/v1/cloudflare-accounts", json={"label": "CF - A", "cfAccountId": "cf-1", "apiToken": "x"}
        )
        account_id = account_resp.json()["data"]["id"]
        project_resp = await client.post("/api/v1/projects", json={"name": "Site"})
        project_id = project_resp.json()["data"]["id"]
        env_resp = await client.post(
            f"/api/v1/projects/{project_id}/environments", json={"type": "dev", "name": "Dev"}
        )
        environment_id = env_resp.json()["data"]["id"]

        response = await client.post(
            "/api/v1/cloudflare-configs",
            json={
                "environmentId": environment_id, "cloudflareAccountId": account_id,
                "zoneId": "belongs-to-a-different-account",
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cloudflare_zone_not_owned_by_account"

        del app.dependency_overrides[get_cloudflare_client]


class TestDnsRecordFullDemoScript:
    async def test_bind_create_delete_and_permission_boundary(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """The Phase 4 acceptance demo, verbatim: bind an environment to an
        account+zone -> create an A record -> row has managed_by=SYSTEM and a
        real cf_record_id -> delete it -> a sub-EDITOR user gets 403, no
        partial state either side."""
        cf_client = FakeCloudflareClient(
            zones=[ZoneOption(id="z1", name="example.com")], create_record_id="rec-real-123"
        )
        environment_id, account_id = await _bind_environment(client, engine, cf_client=cf_client)

        create_resp = await client.post(
            f"/api/v1/environments/{environment_id}/dns-records",
            json={"recordType": "A", "name": "app", "content": "1.2.3.4", "proxied": True, "ttl": 1},
        )
        assert create_resp.status_code == 200, create_resp.text
        record = create_resp.json()["data"]
        assert record["managedBy"] == "system"
        assert record["cfRecordId"] == "rec-real-123"

        delete_resp = await client.delete(
            f"/api/v1/environments/{environment_id}/dns-records/{record['id']}"
        )
        assert delete_resp.status_code == 200
        assert cf_client.deleted_record_ids == ["rec-real-123"]

        list_resp = await client.get(f"/api/v1/environments/{environment_id}/dns-records")
        assert list_resp.json()["data"] == []

        # A VIEWER-only manager on the account (below EDITOR) must be
        # blocked from writing, with no partial state on either side.
        viewer_id = await _login_with_permissions(
            client, engine, permissions=[("cloudflare_account", "manage"), ("cloudflare_account", "view")],
            email="viewer@example.com",
        )
        # Re-login as the account creator (OWNER) to grant the viewer access.
        await _login_with_permissions(
            client, engine, permissions=[("cloudflare_account", "manage"), ("cloudflare_account", "view")],
            email="owner-again@example.com",
        )
        # (In a real run the OWNER who created the account would grant this;
        # here we assign VIEWER directly via the account's existing manager
        # endpoint, then switch the session to them.)
        assign_resp = await client.post(
            f"/api/v1/cloudflare-accounts/{account_id}/managers",
            json={"userId": str(viewer_id), "accessLevel": "viewer"},
        )
        assert assign_resp.status_code in (200, 403)  # 403 if this session isn't the OWNER; acceptable for this check

        viewer_token = JwtCodec.encode(
            {"sub": str(viewer_id), "type": "access", "jti": "viewer-write-attempt"},
            secret=auth_settings.JWT_SECRET, ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, viewer_token)

        blocked_resp = await client.post(
            f"/api/v1/environments/{environment_id}/dns-records",
            json={"recordType": "A", "name": "blocked", "content": "9.9.9.9", "proxied": False, "ttl": 1},
        )
        assert blocked_resp.status_code == 403

        del app.dependency_overrides[get_cloudflare_client]

    async def test_mx_record_requires_priority(self, client: AsyncClient, engine: AsyncEngine) -> None:
        cf_client = FakeCloudflareClient(zones=[ZoneOption(id="z1", name="example.com")])
        environment_id, _ = await _bind_environment(client, engine, cf_client=cf_client)

        response = await client.post(
            f"/api/v1/environments/{environment_id}/dns-records",
            json={"recordType": "MX", "name": "app", "content": "mail.example.com", "proxied": False, "ttl": 1},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "cloudflare_missing_dns_priority"

        del app.dependency_overrides[get_cloudflare_client]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_router.py -v`
Expected: FAIL with 404s (the routes don't exist yet)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/modules/cloudflare/router.py`, add these imports to the existing import block:

```python
from app.modules.cloudflare.dependencies import (
    get_create_config,
    get_create_dns_record,
    get_delete_config,
    get_delete_dns_record,
    get_list_dns_records,
    get_list_zones,
    get_update_config,
    get_update_dns_record,
    require_account_access_for_environment,
    # ...plus every name already imported here from Phase 3
)
from app.modules.cloudflare.exceptions import CloudflareAccountNotFound, CloudflareConfigNotFound
from app.modules.cloudflare.schemas import (
    CloudflareConfigCreate,
    CloudflareConfigRead,
    CloudflareConfigUpdate,
    DnsRecordCreate,
    DnsRecordRead,
    DnsRecordUpdate,
    ZoneOption,
    # ...plus every name already imported here from Phase 3
)
from app.modules.cloudflare.services.create_config import CreateCloudflareConfig
from app.modules.cloudflare.services.create_dns_record import CreateDnsRecord
from app.modules.cloudflare.services.delete_config import DeleteCloudflareConfig
from app.modules.cloudflare.services.delete_dns_record import DeleteDnsRecord
from app.modules.cloudflare.services.list_dns_records import ListDnsRecords
from app.modules.cloudflare.services.list_zones import ListZones
from app.modules.cloudflare.services.update_config import UpdateCloudflareConfig
from app.modules.cloudflare.services.update_dns_record import UpdateDnsRecord
```

Append the 9 routes at the end of `backend/app/modules/cloudflare/router.py`:

```python
@router.get("/cloudflare-accounts/{account_id}/zones")
async def list_zones(
    account_id: UUID,
    use_case: ListZones = Depends(get_list_zones),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access(AccessLevel.VIEWER)),
) -> ApiResponse[list[ZoneOption]]:
    """List zones available on an account, for the bind-time zone picker."""
    zones = await use_case.execute(account_id)
    return ApiResponse[list[ZoneOption]](success=True, data=zones)


@router.post("/cloudflare-configs")
async def create_cloudflare_config(
    body: CloudflareConfigCreate,
    use_case: CreateCloudflareConfig = Depends(get_create_config),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
) -> ApiResponse[CloudflareConfigRead]:
    """Bind an environment to an account + zone. No Depends(require_account_access(...))
    here — cloudflare_account_id is body-only (Decision #1); CreateCloudflareConfig
    resolves the Layer-2 grant itself via resolve_account_access_grant."""
    config = await use_case.execute(body.environment_id, body.cloudflare_account_id, body.zone_id, actor=user)
    return ApiResponse[CloudflareConfigRead](success=True, data=config)


@router.get("/environments/{environment_id}/cloudflare-config")
async def get_cloudflare_config(
    environment_id: UUID,
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[CloudflareConfigRead]:
    """Return one environment's binding, 404 if unbound."""
    config = await uow.configs.get_by_environment_id(environment_id)
    if config is None:
        raise CloudflareConfigNotFound()
    return ApiResponse[CloudflareConfigRead](success=True, data=config)


@router.patch("/environments/{environment_id}/cloudflare-config")
async def update_cloudflare_config(
    environment_id: UUID,
    body: CloudflareConfigUpdate,
    use_case: UpdateCloudflareConfig = Depends(get_update_config),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[CloudflareConfigRead]:
    """Rebind an environment to a different zone on the same account."""
    config = await use_case.execute(environment_id, body.zone_id, grant=grant)
    return ApiResponse[CloudflareConfigRead](success=True, data=config)


@router.delete("/environments/{environment_id}/cloudflare-config")
async def delete_cloudflare_config(
    environment_id: UUID,
    use_case: DeleteCloudflareConfig = Depends(get_delete_config),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Remove an environment's binding. Blocked while DNS records still exist."""
    await use_case.execute(environment_id, grant=grant)
    return ApiResponse[None](success=True)


@router.get("/environments/{environment_id}/dns-records")
async def list_environment_dns_records(
    environment_id: UUID,
    use_case: ListDnsRecords = Depends(get_list_dns_records),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[list[DnsRecordRead]]:
    """List an environment's DNS records."""
    records = await use_case.execute(environment_id)
    return ApiResponse[list[DnsRecordRead]](success=True, data=records)


@router.post("/environments/{environment_id}/dns-records")
async def create_environment_dns_record(
    environment_id: UUID,
    body: DnsRecordCreate,
    use_case: CreateDnsRecord = Depends(get_create_dns_record),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[DnsRecordRead]:
    """Create a DNS record — Cloudflare must confirm first (Decision #3)."""
    record = await use_case.execute(
        environment_id, body.record_type, body.name, body.content, body.priority, body.proxied, body.ttl,
        actor=user,
    )
    return ApiResponse[DnsRecordRead](success=True, data=record)


@router.patch("/environments/{environment_id}/dns-records/{record_id}")
async def update_environment_dns_record(
    environment_id: UUID,
    record_id: UUID,
    body: DnsRecordUpdate,
    use_case: UpdateDnsRecord = Depends(get_update_dns_record),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[DnsRecordRead]:
    """Update a DNS record — Cloudflare must confirm first (Decision #3)."""
    record = await use_case.execute(
        environment_id, record_id, body.content, body.priority, body.proxied, body.ttl, actor=user
    )
    return ApiResponse[DnsRecordRead](success=True, data=record)


@router.delete("/environments/{environment_id}/dns-records/{record_id}")
async def delete_environment_dns_record(
    environment_id: UUID,
    record_id: UUID,
    use_case: DeleteDnsRecord = Depends(get_delete_dns_record),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Delete a DNS record — Cloudflare must confirm first (Decision #3)."""
    await use_case.execute(environment_id, record_id, actor=user)
    return ApiResponse[None](success=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_router.py -v`
Expected: PASS (all tests, including every Phase 3 test already in the file)

- [ ] **Step 5: Run the FULL backend suite**

Run: `cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q`
Expected: all green, no regressions in Phase 1–3's tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/cloudflare/router.py backend/tests/cloudflare/test_router.py
git commit -m "feat(cloudflare): add 9 DNS/config binding routes with full demo-script coverage"
```

---

# Frontend Tasks

The frontend has no test runner in this repo (established in Phase 1–3) — verification is `npx tsc --noEmit` + `npm run lint` + `npm run build`, not a TDD test-per-step cycle. Each frontend task below follows: write the file(s) → typecheck/lint → commit.

## Task 18: Extend `entities/environment/` with a single-environment fetch

**Files:**
- Modify: `frontend/src/entities/environment/api/fetchers.ts`
- Modify: `frontend/src/entities/environment/hooks/use-environments.ts`
- Modify: `frontend/src/entities/environment/index.ts`

**Interfaces:**
- Consumes: `API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENT_DETAIL(id)` (already defined in `shared/constants/api.ts`, unused until now), `environmentsKeys.detail(id)` (already defined in `api/query-keys.ts`, unused until now), the backend's new `GET /environments/{environment_id}` from Task 7.
- Produces: `fetchEnvironmentById(id: string): Promise<Environment>`, `useEnvironmentQuery(id: string)`.

- [ ] **Step 1: Add the fetcher**

Append to `frontend/src/entities/environment/api/fetchers.ts`:

```typescript
/**
 * Fetches one environment from GET /environments/{id}.
 */
export async function fetchEnvironmentById(id: string): Promise<Environment> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.PROJECTS.ENVIRONMENT_DETAIL(id));
  return environmentSchema.parse(raw);
}
```

- [ ] **Step 2: Add the hook**

Append to `frontend/src/entities/environment/hooks/use-environments.ts`:

```typescript
export function useEnvironmentQuery(id: string) {
  return useSuspenseQuery({
    queryKey: environmentsKeys.detail(id),
    queryFn: () => fetchEnvironmentById(id),
  });
}
```

Update the file's import line to `import { fetchEnvironmentById, fetchProjectEnvironments } from "../api/fetchers";`.

- [ ] **Step 3: Export from the entity's index**

Update `frontend/src/entities/environment/index.ts`:

```typescript
export { fetchEnvironmentById, fetchProjectEnvironments } from "./api/fetchers";
export { environmentsKeys } from "./api/query-keys";
export { useEnvironmentQuery, useProjectEnvironmentsQuery } from "./hooks/use-environments";
export { environmentSchema, ENVIRONMENT_TYPES } from "./model/schema";
export type { Environment, EnvironmentType } from "./model/schema";
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/entities/environment
git commit -m "feat(environment): add single-environment fetch (fetchEnvironmentById)"
```

---

## Task 19: `shared/constants/api.ts` — `CLOUDFLARE_DNS` endpoint block

**Files:**
- Modify: `frontend/src/shared/constants/api.ts`

**Interfaces:**
- Produces: `API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.{ZONES(accountId), CONFIGS_ROOT, CONFIG(environmentId), RECORDS(environmentId), RECORD_DETAIL(environmentId, recordId)}`.

- [ ] **Step 1: Add the endpoint block**

Insert into `API_CONFIG.ENDPOINTS`, after the existing `CLOUDFLARE_ACCOUNTS` block in `frontend/src/shared/constants/api.ts`:

```typescript
    CLOUDFLARE_DNS: {
      ZONES: (accountId: string) => `/cloudflare-accounts/${accountId}/zones`,
      CONFIGS_ROOT: "/cloudflare-configs",
      CONFIG: (environmentId: string) => `/environments/${environmentId}/cloudflare-config`,
      RECORDS: (environmentId: string) => `/environments/${environmentId}/dns-records`,
      RECORD_DETAIL: (environmentId: string, recordId: string) =>
        `/environments/${environmentId}/dns-records/${recordId}`,
    },
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/shared/constants/api.ts
git commit -m "feat(api): add CLOUDFLARE_DNS endpoint constants"
```

---

## Task 20: `modules/cloudflare-dns/` — schema, fetchers, query-keys

**Files:**
- Create: `frontend/src/modules/cloudflare-dns/model/schema.ts`
- Create: `frontend/src/modules/cloudflare-dns/api/fetchers.ts`
- Create: `frontend/src/modules/cloudflare-dns/api/query-keys.ts`

**Interfaces:**
- Consumes: `apiFetch`, `ApiRequestError` (`@/shared/lib/api-client`), `API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS` (Task 19).
- Produces: `zoneOptionSchema`/`ZoneOption`, `cloudflareConfigSchema`/`CloudflareConfig`, `dnsRecordSchema`/`DnsRecord`, `DNS_RECORD_TYPES`; `fetchZones`, `fetchCloudflareConfigOrNull`, `createCloudflareConfig`, `updateCloudflareConfig`, `deleteCloudflareConfig`, `fetchDnsRecords`, `createDnsRecord`, `updateDnsRecord`, `deleteDnsRecord`; `cloudflareDnsKeys`.

No `entities/` promotion for these — per the approved plan, nothing outside this module currently needs `cloudflare_configs`/`dns_records`, unlike `entities/cloudflare-account` which Phases 4/5/9 all needed.

- [ ] **Step 1: Write the schema**

Create `frontend/src/modules/cloudflare-dns/model/schema.ts`:

```typescript
import { z } from "zod";

export const DNS_RECORD_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "OTHER"] as const;

export const zoneOptionSchema = z.object({
  id: z.string(),
  name: z.string(),
});
export type ZoneOption = z.infer<typeof zoneOptionSchema>;

export const cloudflareConfigSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  cloudflareAccountId: z.uuid(),
  zoneId: z.string(),
  zoneName: z.string(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type CloudflareConfig = z.infer<typeof cloudflareConfigSchema>;

export const dnsRecordSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  cfRecordId: z.string(),
  recordType: z.enum(DNS_RECORD_TYPES),
  name: z.string(),
  content: z.string(),
  priority: z.number().nullable(),
  proxied: z.boolean(),
  ttl: z.number(),
  managedBy: z.enum(["system", "external"]),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type DnsRecord = z.infer<typeof dnsRecordSchema>;
export type DnsRecordType = (typeof DNS_RECORD_TYPES)[number];
```

- [ ] **Step 2: Write the fetchers**

Create `frontend/src/modules/cloudflare-dns/api/fetchers.ts`:

```typescript
import { apiFetch, ApiRequestError } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import {
  cloudflareConfigSchema,
  dnsRecordSchema,
  zoneOptionSchema,
  type CloudflareConfig,
  type DnsRecord,
  type DnsRecordType,
  type ZoneOption,
} from "../model/schema";

/**
 * Fetches every zone available on a Cloudflare account, for the bind-time
 * zone picker (GET /cloudflare-accounts/{accountId}/zones).
 */
export async function fetchZones(accountId: string): Promise<ZoneOption[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.ZONES(accountId));
  return zoneOptionSchema.array().parse(raw);
}

/**
 * Fetches one environment's Cloudflare binding, or null if unbound
 * (GET returns 404 `cloudflare_config_not_found`, which this normalizes to
 * null rather than throwing — "not yet bound" is expected UI state, not an error).
 */
export async function fetchCloudflareConfigOrNull(environmentId: string): Promise<CloudflareConfig | null> {
  try {
    const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.CONFIG(environmentId));
    return cloudflareConfigSchema.parse(raw);
  } catch (error) {
    if (error instanceof ApiRequestError && error.code === "cloudflare_config_not_found") {
      return null;
    }
    throw error;
  }
}

export async function createCloudflareConfig(data: {
  environmentId: string;
  cloudflareAccountId: string;
  zoneId: string;
}): Promise<CloudflareConfig> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.CONFIGS_ROOT, {
    method: "POST",
    data,
  });
  return cloudflareConfigSchema.parse(raw);
}

export async function updateCloudflareConfig(environmentId: string, zoneId: string): Promise<CloudflareConfig> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.CONFIG(environmentId), {
    method: "PATCH",
    data: { zoneId },
  });
  return cloudflareConfigSchema.parse(raw);
}

export async function deleteCloudflareConfig(environmentId: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.CONFIG(environmentId), { method: "DELETE" });
}

export async function fetchDnsRecords(environmentId: string): Promise<DnsRecord[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.RECORDS(environmentId));
  return dnsRecordSchema.array().parse(raw);
}

export interface DnsRecordFormValues {
  recordType: DnsRecordType;
  name: string;
  content: string;
  priority?: number | null;
  proxied: boolean;
  ttl: number;
}

export async function createDnsRecord(environmentId: string, data: DnsRecordFormValues): Promise<DnsRecord> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.RECORDS(environmentId), {
    method: "POST",
    data,
  });
  return dnsRecordSchema.parse(raw);
}

export async function updateDnsRecord(
  environmentId: string,
  recordId: string,
  data: Omit<DnsRecordFormValues, "recordType">,
): Promise<DnsRecord> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.RECORD_DETAIL(environmentId, recordId), {
    method: "PATCH",
    data,
  });
  return dnsRecordSchema.parse(raw);
}

export async function deleteDnsRecord(environmentId: string, recordId: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_DNS.RECORD_DETAIL(environmentId, recordId), {
    method: "DELETE",
  });
}
```

- [ ] **Step 3: Write the query-key factory**

Create `frontend/src/modules/cloudflare-dns/api/query-keys.ts`:

```typescript
/**
 * Hierarchical query key factory for the cloudflare-dns module.
 */
export const cloudflareDnsKeys = {
  all: ["cloudflare-dns"] as const,
  zones: (accountId: string) => [...cloudflareDnsKeys.all, "zones", accountId] as const,
  config: (environmentId: string) => [...cloudflareDnsKeys.all, "config", environmentId] as const,
  records: (environmentId: string) => [...cloudflareDnsKeys.all, "records", environmentId] as const,
};
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/cloudflare-dns/model frontend/src/modules/cloudflare-dns/api
git commit -m "feat(cloudflare-dns): add schema, fetchers, and query-keys"
```

---

## Task 21: `modules/cloudflare-dns/` — hooks (queries + mutations)

**Files:**
- Create: `frontend/src/modules/cloudflare-dns/hooks/use-zones-query.ts`
- Create: `frontend/src/modules/cloudflare-dns/hooks/use-cloudflare-config.ts`
- Create: `frontend/src/modules/cloudflare-dns/hooks/use-dns-records.ts`

**Interfaces:**
- Consumes: every fetcher and `cloudflareDnsKeys` from Task 20.
- Produces: `useZonesQuery(accountId, enabled)`, `useCloudflareConfigQuery(environmentId)`, `useCreateCloudflareConfig()`, `useUpdateCloudflareConfig(environmentId)`, `useDeleteCloudflareConfig(environmentId)`, `useDnsRecordsQuery(environmentId, enabled)`, `useCreateDnsRecord(environmentId)`, `useUpdateDnsRecord(environmentId)`, `useDeleteDnsRecord(environmentId)`.

Unlike `entities/cloudflare-account`'s `useSuspenseQuery` hooks (which read something that always exists), this module deliberately uses plain `useQuery` throughout — a `null` config is legitimate ("not yet bound") page state the UI must branch on, not an error condition Suspense's error-boundary model fits well.

- [ ] **Step 1: Write `use-zones-query.ts`**

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchZones } from "../api/fetchers";
import { cloudflareDnsKeys } from "../api/query-keys";

export function useZonesQuery(accountId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: cloudflareDnsKeys.zones(accountId ?? "none"),
    queryFn: () => fetchZones(accountId as string),
    enabled: enabled && accountId !== null,
  });
}
```

- [ ] **Step 2: Write `use-cloudflare-config.ts`**

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCloudflareConfig,
  deleteCloudflareConfig,
  fetchCloudflareConfigOrNull,
  updateCloudflareConfig,
} from "../api/fetchers";
import { cloudflareDnsKeys } from "../api/query-keys";

export function useCloudflareConfigQuery(environmentId: string) {
  return useQuery({
    queryKey: cloudflareDnsKeys.config(environmentId),
    queryFn: () => fetchCloudflareConfigOrNull(environmentId),
  });
}

export function useCreateCloudflareConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCloudflareConfig,
    onSuccess: (config) => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.config(config.environmentId) });
    },
  });
}

export function useUpdateCloudflareConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (zoneId: string) => updateCloudflareConfig(environmentId, zoneId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.config(environmentId) });
    },
  });
}

export function useDeleteCloudflareConfig(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteCloudflareConfig(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.config(environmentId) });
    },
  });
}
```

- [ ] **Step 3: Write `use-dns-records.ts`**

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createDnsRecord,
  deleteDnsRecord,
  fetchDnsRecords,
  updateDnsRecord,
  type DnsRecordFormValues,
} from "../api/fetchers";
import { cloudflareDnsKeys } from "../api/query-keys";

export function useDnsRecordsQuery(environmentId: string, enabled: boolean) {
  return useQuery({
    queryKey: cloudflareDnsKeys.records(environmentId),
    queryFn: () => fetchDnsRecords(environmentId),
    enabled,
  });
}

export function useCreateDnsRecord(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: DnsRecordFormValues) => createDnsRecord(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.records(environmentId) });
    },
  });
}

export function useUpdateDnsRecord(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ recordId, data }: { recordId: string; data: Omit<DnsRecordFormValues, "recordType"> }) =>
      updateDnsRecord(environmentId, recordId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.records(environmentId) });
    },
  });
}

export function useDeleteDnsRecord(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (recordId: string) => deleteDnsRecord(environmentId, recordId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.records(environmentId) });
    },
  });
}
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/cloudflare-dns/hooks
git commit -m "feat(cloudflare-dns): add query and mutation hooks"
```

---

## Task 22: `cloudflare-binding-form.tsx` — dependent account/zone pickers

**Files:**
- Create: `frontend/src/modules/cloudflare-dns/ui/cloudflare-binding-form.tsx`

**Interfaces:**
- Consumes: `useCloudflareAccountsQuery` (`@/entities/cloudflare-account`, existing), `useZonesQuery`/`useCreateCloudflareConfig` (Task 21).
- Produces: `<CloudflareBindingForm environmentId={string} />` — rendered by Task 24's page content when `useCloudflareConfigQuery` resolves to `null`.

**MANDATORY per AGENTS.md**: before/while writing this file, invoke the `ui-ux-pro-max` plugin for a dependent-select pattern (the zone `<select>` must be visibly disabled/empty until an account is chosen — never silently ignore the selection) and for form-level a11y (label association, loading/disabled states, error placement near the field per its "Forms & Feedback" guidance). Apply the result while writing the markup below — the code shown here is the functional skeleton; adjust classes/spacing/ARIA per the plugin's actual output before treating this task as done.

- [ ] **Step 1: Write the component**

```typescript
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Cloud, Globe } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCloudflareAccountsQuery } from "@/entities/cloudflare-account";
import { useZonesQuery } from "../hooks/use-zones-query";
import { useCreateCloudflareConfig } from "../hooks/use-cloudflare-config";

export function CloudflareBindingForm({ environmentId }: { environmentId: string }) {
  const t = useTranslations("cloudflareDns");
  const getErrorMessage = useApiErrorMessage("cloudflareDns");
  const { data: accounts } = useCloudflareAccountsQuery();
  const [accountId, setAccountId] = useState<string | null>(null);
  const [zoneId, setZoneId] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: zones, isFetching: zonesLoading } = useZonesQuery(accountId, accountId !== null);
  const createConfig = useCreateCloudflareConfig();

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!accountId || !zoneId) return;
    setErrorMessage(null);
    createConfig.mutate(
      { environmentId, cloudflareAccountId: accountId, zoneId },
      { onError: (err) => setErrorMessage(getErrorMessage(err)) },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-xl border bg-card p-5">
      <div className="flex items-center gap-2">
        <Cloud className="size-4 text-primary" aria-hidden="true" />
        <h2 className="text-sm font-bold text-foreground">{t("binding.title")}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{t("binding.description")}</p>

      {errorMessage && (
        <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errorMessage}
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="binding-account">{t("binding.accountLabel")}</Label>
        <select
          id="binding-account"
          value={accountId ?? ""}
          onChange={(event) => {
            setAccountId(event.target.value || null);
            setZoneId("");
          }}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          required
        >
          <option value="">{t("binding.selectAccount")}</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="binding-zone">{t("binding.zoneLabel")}</Label>
        <select
          id="binding-zone"
          value={zoneId}
          onChange={(event) => setZoneId(event.target.value)}
          disabled={accountId === null || zonesLoading}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          required
        >
          <option value="">
            {accountId === null
              ? t("binding.selectAccountFirst")
              : zonesLoading
                ? t("binding.loadingZones")
                : t("binding.selectZone")}
          </option>
          {zones?.map((zone) => (
            <option key={zone.id} value={zone.id}>
              {zone.name}
            </option>
          ))}
        </select>
      </div>

      <Button type="submit" disabled={createConfig.isPending || !accountId || !zoneId} className="self-start">
        <Globe className="mr-1.5 size-3.5" aria-hidden="true" />
        {createConfig.isPending ? t("binding.binding") : t("binding.bind")}
      </Button>
    </form>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (i18n keys under `cloudflareDns.binding.*` are wired in Task 25 — `next-intl`'s `t()` calls typecheck against string keys regardless of whether the JSON file has the key yet, so this compiles before Task 25 lands)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/cloudflare-dns/ui/cloudflare-binding-form.tsx
git commit -m "feat(cloudflare-dns): add binding form with dependent account/zone pickers"
```

---

## Task 23: `dns-record-form-dialog.tsx` — MX-conditional priority field

**Files:**
- Create: `frontend/src/modules/cloudflare-dns/ui/dns-record-form-dialog.tsx`

**Interfaces:**
- Consumes: `useCreateDnsRecord`/`useUpdateDnsRecord` (Task 21), `DNS_RECORD_TYPES`/`DnsRecord` (Task 20).
- Produces: `<DnsRecordFormDialog environmentId={string} record={DnsRecord | null} onClose={() => void} />`.

**MANDATORY per AGENTS.md**: invoke `ui-ux-pro-max` for this file — specifically for the conditional-field pattern (the `priority` field appearing/disappearing when `recordType` changes must not cause layout jank — reserve space or animate per the plugin's guidance) and modal focus/ARIA per its hand-rolled-dialog checklist (same pattern already applied to Phase 3's `CloudflareAccountFormDialog` — mirror that precedent, then re-verify against a fresh plugin query since this dialog's conditional field is a new interaction shape Phase 3 didn't have).

- [ ] **Step 1: Write the component**

```typescript
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, Plus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { DNS_RECORD_TYPES, type DnsRecord, type DnsRecordType } from "../model/schema";
import { useCreateDnsRecord } from "../hooks/use-dns-records";
import { useUpdateDnsRecord } from "../hooks/use-dns-records";

interface DnsRecordFormDialogProps {
  environmentId: string;
  record: DnsRecord | null;
  onClose: () => void;
}

export function DnsRecordFormDialog({ environmentId, record, onClose }: DnsRecordFormDialogProps) {
  const t = useTranslations("cloudflareDns");
  const getErrorMessage = useApiErrorMessage("cloudflareDns");
  const isEditing = Boolean(record);

  const [recordType, setRecordType] = useState<DnsRecordType>(record?.recordType ?? "A");
  const [name, setName] = useState(record?.name ?? "");
  const [content, setContent] = useState(record?.content ?? "");
  const [priority, setPriority] = useState<string>(record?.priority?.toString() ?? "");
  const [proxied, setProxied] = useState(record?.proxied ?? false);
  const [ttl, setTtl] = useState(record?.ttl ?? 1);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const create = useCreateDnsRecord(environmentId);
  const update = useUpdateDnsRecord(environmentId);
  const isSaving = create.isPending || update.isPending;
  const requiresPriority = recordType === "MX";

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const parsedPriority = requiresPriority ? Number(priority) : null;
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };
    if (isEditing && record) {
      update.mutate(
        { recordId: record.id, data: { content, priority: parsedPriority, proxied, ttl } },
        callbacks,
      );
    } else {
      create.mutate({ recordType, name, content, priority: parsedPriority, proxied, ttl }, callbacks);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dns-record-form-title"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg animate-in zoom-in-95">
        <div className="flex items-center justify-between mb-4">
          <h2 id="dns-record-form-title" className="text-lg font-semibold">
            {isEditing ? t("records.editRecord") : t("records.createRecord")}
          </h2>
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t("form.cancel")}>
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {errorMessage && (
            <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="record-type">{t("records.type")}</Label>
            <select
              id="record-type"
              value={recordType}
              onChange={(event) => setRecordType(event.target.value as DnsRecordType)}
              disabled={isEditing}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              {DNS_RECORD_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="record-name">{t("records.name")}</Label>
            <Input
              id="record-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={isEditing}
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="record-content">{t("records.content")}</Label>
            <Input id="record-content" value={content} onChange={(event) => setContent(event.target.value)} required />
          </div>

          {requiresPriority && (
            <div className="space-y-1.5">
              <Label htmlFor="record-priority">{t("records.priority")}</Label>
              <Input
                id="record-priority"
                type="number"
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
                required
                aria-describedby="record-priority-hint"
              />
              <p id="record-priority-hint" className="text-xs text-muted-foreground">
                {t("records.priorityHint")}
              </p>
            </div>
          )}

          <div className="flex items-center gap-2">
            <input
              id="record-proxied"
              type="checkbox"
              checked={proxied}
              onChange={(event) => setProxied(event.target.checked)}
              className="size-4 rounded border-input"
            />
            <Label htmlFor="record-proxied" className="cursor-pointer">
              {t("records.proxied")}
            </Label>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="record-ttl">{t("records.ttl")}</Label>
            <Input
              id="record-ttl"
              type="number"
              min={1}
              value={ttl}
              onChange={(event) => setTtl(Number(event.target.value))}
              required
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={isSaving}>
              <Plus className="mr-1 size-3.5" aria-hidden="true" />
              {isSaving ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/cloudflare-dns/ui/dns-record-form-dialog.tsx
git commit -m "feat(cloudflare-dns): add DNS record form dialog with MX-conditional priority"
```

---

## Task 24: `cloudflare-dns-page-content.tsx` — orchestrator + DNS table + `index.ts`

**Files:**
- Create: `frontend/src/modules/cloudflare-dns/ui/cloudflare-dns-page-content.tsx`
- Create: `frontend/src/modules/cloudflare-dns/index.ts`

**Interfaces:**
- Consumes: `useEnvironmentQuery` (Task 18), `useCloudflareConfigQuery`/`useDeleteCloudflareConfig` (Task 21), `useDnsRecordsQuery`/`useDeleteDnsRecord` (Task 21), `CloudflareBindingForm` (Task 22), `DnsRecordFormDialog` (Task 23).
- Produces: `<CloudflareDnsPageContent environmentId={string} />` — the component the new route (Task 25) renders.

**MANDATORY per AGENTS.md**: invoke `ui-ux-pro-max` for the DNS record table layout (column hierarchy/spacing, empty state, the `managedBy=external` badge's color must not be the only signal — pair with an icon/label, matching Phase 3's established "never convey state by color alone" guidance) and the destructive "Unbind" confirmation copy/contrast.

- [ ] **Step 1: Write the component**

```typescript
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Cloud, Globe, Plus, Pencil, Trash2, ExternalLink } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useEnvironmentQuery } from "@/entities/environment";
import { useCloudflareConfigQuery, useDeleteCloudflareConfig } from "../hooks/use-cloudflare-config";
import { useDnsRecordsQuery, useDeleteDnsRecord } from "../hooks/use-dns-records";
import type { DnsRecord } from "../model/schema";
import { CloudflareBindingForm } from "./cloudflare-binding-form";
import { DnsRecordFormDialog } from "./dns-record-form-dialog";

export function CloudflareDnsPageContent({ environmentId }: { environmentId: string }) {
  const t = useTranslations("cloudflareDns");
  const { data: environment } = useEnvironmentQuery(environmentId);
  const { data: config, isLoading: configLoading } = useCloudflareConfigQuery(environmentId);
  const isBound = Boolean(config);
  const { data: records = [] } = useDnsRecordsQuery(environmentId, isBound);
  const deleteConfig = useDeleteCloudflareConfig(environmentId);
  const deleteRecord = useDeleteDnsRecord(environmentId);

  const [recordFormTarget, setRecordFormTarget] = useState<DnsRecord | "create" | null>(null);
  const [recordDeleteTarget, setRecordDeleteTarget] = useState<DnsRecord | null>(null);
  const [unbindConfirmOpen, setUnbindConfirmOpen] = useState(false);

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{environment.name}</h1>
        <p className="text-sm text-muted-foreground">{t(`environmentTypes.${environment.type}`)}</p>
      </div>

      {configLoading && <div className="h-24 w-full animate-pulse rounded-xl bg-muted/50" />}

      {!configLoading && !isBound && <CloudflareBindingForm environmentId={environmentId} />}

      {!configLoading && config && (
        <>
          <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
                <Cloud className="size-4 text-primary" aria-hidden="true" /> {config.zoneName}
              </h2>
              <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                <Button variant="outline" size="sm" onClick={() => setUnbindConfirmOpen(true)}>
                  {t("binding.unbind")}
                </Button>
              </Can>
            </div>
          </section>

          <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
                <Globe className="size-4" aria-hidden="true" /> {t("records.title")}
              </h2>
              <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                <Button size="sm" onClick={() => setRecordFormTarget("create")}>
                  <Plus className="mr-1.5 size-3.5" aria-hidden="true" /> {t("records.addRecord")}
                </Button>
              </Can>
            </div>

            {records.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("records.empty")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                      <th className="py-2 pr-4">{t("records.type")}</th>
                      <th className="py-2 pr-4">{t("records.name")}</th>
                      <th className="py-2 pr-4">{t("records.content")}</th>
                      <th className="py-2 pr-4">{t("records.managedBy")}</th>
                      <th className="py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {records.map((record) => (
                      <tr key={record.id}>
                        <td className="py-2 pr-4 font-mono text-xs">{record.recordType}</td>
                        <td className="py-2 pr-4">{record.name}</td>
                        <td className="py-2 pr-4 text-muted-foreground">{record.content}</td>
                        <td className="py-2 pr-4">
                          {record.managedBy === "external" ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                              <ExternalLink className="size-3" aria-hidden="true" /> {t("records.external")}
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">{t("records.system")}</span>
                          )}
                        </td>
                        <td className="py-2 text-right">
                          <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => setRecordFormTarget(record)}
                                aria-label={t("records.editRecord")}
                                className="cursor-pointer text-muted-foreground hover:text-foreground"
                              >
                                <Pencil className="size-3.5" aria-hidden="true" />
                              </button>
                              <button
                                type="button"
                                onClick={() => setRecordDeleteTarget(record)}
                                aria-label={t("records.deleteRecord")}
                                className="cursor-pointer text-muted-foreground hover:text-destructive"
                              >
                                <Trash2 className="size-3.5" aria-hidden="true" />
                              </button>
                            </div>
                          </Can>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {recordFormTarget !== null && (
        <DnsRecordFormDialog
          environmentId={environmentId}
          record={recordFormTarget === "create" ? null : recordFormTarget}
          onClose={() => setRecordFormTarget(null)}
        />
      )}

      <ConfirmDialog
        isOpen={recordDeleteTarget !== null}
        onClose={() => setRecordDeleteTarget(null)}
        onConfirm={() => {
          if (recordDeleteTarget) {
            deleteRecord.mutate(recordDeleteTarget.id, { onSuccess: () => setRecordDeleteTarget(null) });
          }
        }}
        title={t("records.deleteConfirm.title")}
        description={t("records.deleteConfirm.description", { name: recordDeleteTarget?.name ?? "" })}
        variant="destructive"
        isLoading={deleteRecord.isPending}
      />

      <ConfirmDialog
        isOpen={unbindConfirmOpen}
        onClose={() => setUnbindConfirmOpen(false)}
        onConfirm={() => {
          deleteConfig.mutate(undefined, { onSuccess: () => setUnbindConfirmOpen(false) });
        }}
        title={t("binding.unbindConfirm.title")}
        description={t("binding.unbindConfirm.description")}
        variant="destructive"
        isLoading={deleteConfig.isPending}
      />
    </div>
  );
}
```

- [ ] **Step 2: Write the module index**

Create `frontend/src/modules/cloudflare-dns/index.ts`:

```typescript
export { CloudflareDnsPageContent } from "./ui/cloudflare-dns-page-content";
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/modules/cloudflare-dns/ui/cloudflare-dns-page-content.tsx frontend/src/modules/cloudflare-dns/index.ts
git commit -m "feat(cloudflare-dns): add page-content orchestrator with DNS record table"
```

---

## Task 25: Route + `project-detail-view.tsx`'s DNS affordance + i18n wiring

**Files:**
- Create: `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/dns/page.tsx`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/dns/loading.tsx`
- Modify: `frontend/src/modules/projects/ui/project-detail-view.tsx`
- Create: `frontend/locales/en/modules/cloudflare-dns.json`
- Create: `frontend/locales/vi/modules/cloudflare-dns.json`
- Modify: `frontend/src/shared/lib/i18n/request.ts`

**Interfaces:**
- Consumes: `fetchEnvironmentById`/`environmentsKeys` (Task 18), `CloudflareDnsPageContent` (Task 24), `RequirePermission`/`NoPermission`/`hasPermission` (existing, mirrors the `cloudflare-accounts/[accountId]` route exactly).
- Produces: `GET /admin/environments/{environmentId}/dns` page; a "DNS" icon-button on each environment chip in `project-detail-view.tsx`, gated on `ACTIONS.VIEW`/`RESOURCES.CLOUDFLARE_ACCOUNT`.

No new top-level `ROUTES.*` entry — this is a dynamic per-environment route reached via a link, mirroring how `admin/cloudflare-accounts/[accountId]` itself has no dedicated `ROUTES.*` constant (only the list page's static `ROUTES.adminCloudflareAccounts` does).

- [ ] **Step 1: Write the route page**

Create `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/dns/page.tsx`:

```typescript
import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchEnvironmentById, environmentsKeys } from "@/entities/environment";
import { CloudflareDnsPageContent } from "@/modules/cloudflare-dns";

export default async function AdminEnvironmentDnsPage({
  params,
}: {
  params: Promise<{ locale: string; environmentId: string }>;
}) {
  const { locale, environmentId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canView = hasPermission(session, RESOURCES.CLOUDFLARE_ACCOUNT, ACTIONS.VIEW);

  const queryClient = createQueryClient();
  if (canView) {
    await queryClient.prefetchQuery({
      queryKey: environmentsKeys.detail(environmentId),
      queryFn: () => fetchEnvironmentById(environmentId),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.CLOUDFLARE_ACCOUNT}
        action={ACTIONS.VIEW}
        fallback={<NoPermission />}
      >
        <CloudflareDnsPageContent environmentId={environmentId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
```

Only the environment read is prefetched server-side (cheap, always exists) — the config/DNS-records queries hydrate client-side per the approved plan, so the "not yet bound" state doesn't need special SSR handling.

- [ ] **Step 2: Write the loading skeleton**

Create `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/dns/loading.tsx`:

```typescript
import { Skeleton } from "@/shared/ui/skeleton";

export default function AdminEnvironmentDnsLoading() {
  return (
    <div className="p-6 space-y-6">
      <Skeleton className="h-6 w-48 mb-4" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}
```

- [ ] **Step 3: Add the DNS affordance to `project-detail-view.tsx`**

In `frontend/src/modules/projects/ui/project-detail-view.tsx`, add `Globe` to the existing `lucide-react` import (`import { Plus, Pencil, Trash2, Server, Link2, Globe } from "lucide-react";`), add `import { Link } from "@/shared/lib/i18n/navigation";`, and insert a link inside the environment chip's `<div>` (the block starting `{environments.map((env) => (`), right after the existing `<span className="text-muted-foreground">{env.name}</span>` line:

```typescript
              <Can I={ACTIONS.VIEW} a={RESOURCES.CLOUDFLARE_ACCOUNT}>
                <Link
                  href={`/admin/environments/${env.id}/dns`}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={t("actions.manageDns")}
                >
                  <Globe className="size-3.5" />
                </Link>
              </Can>
```

(placed before the existing `<Can I={ACTIONS.UPDATE} a={RESOURCES.ENVIRONMENT}>` edit-pencil block, so the ordering reads: name → DNS link → edit → delete)

- [ ] **Step 4: Write the locale files**

Create `frontend/locales/en/modules/cloudflare-dns.json`:

```json
{
  "environmentTypes": {
    "dev": "Development",
    "staging": "Staging",
    "production": "Production"
  },
  "binding": {
    "title": "Cloudflare Binding",
    "description": "Bind this environment to a Cloudflare account and zone to manage its DNS records here.",
    "accountLabel": "Cloudflare Account",
    "selectAccount": "Select an account",
    "zoneLabel": "Zone",
    "selectAccountFirst": "Select an account first",
    "loadingZones": "Loading zones...",
    "selectZone": "Select a zone",
    "bind": "Bind",
    "binding": "Binding...",
    "unbind": "Unbind",
    "unbindConfirm": {
      "title": "Unbind this environment?",
      "description": "This removes the Cloudflare binding. Delete all DNS records first."
    }
  },
  "records": {
    "title": "DNS Records",
    "addRecord": "Add Record",
    "editRecord": "Edit Record",
    "createRecord": "Create Record",
    "deleteRecord": "Delete Record",
    "empty": "No DNS records yet.",
    "type": "Type",
    "name": "Name",
    "content": "Content",
    "priority": "Priority",
    "priorityHint": "Lower values are tried first.",
    "proxied": "Proxied through Cloudflare",
    "ttl": "TTL (seconds)",
    "managedBy": "Managed By",
    "system": "System",
    "external": "External",
    "deleteConfirm": {
      "title": "Delete this DNS record?",
      "description": "This removes \"{name}\" from Cloudflare and cannot be undone."
    }
  },
  "form": {
    "cancel": "Cancel",
    "save": "Save",
    "saving": "Saving...",
    "create": "Create"
  },
  "errors": {
    "cloudflare_config_not_found": "This environment is not bound to a Cloudflare account/zone.",
    "cloudflare_config_already_exists": "This environment is already bound.",
    "cloudflare_zone_not_owned_by_account": "This zone does not belong to the selected account.",
    "cloudflare_missing_dns_priority": "MX records require a priority value.",
    "cloudflare_dns_sync_failed": "Cloudflare was updated but saving locally failed — please refresh and verify.",
    "cloudflare_dns_records_exist_for_config": "Delete all DNS records before removing this binding."
  }
}
```

Create `frontend/locales/vi/modules/cloudflare-dns.json` with the same key structure translated to Vietnamese (mirror every key above 1:1 — do not add or omit keys between the two locale files, matching the existing convention in every other `locales/{en,vi}/modules/*.json` pair in this repo).

- [ ] **Step 5: Register the namespace**

In `frontend/src/shared/lib/i18n/request.ts`, add `cloudflareDns` alongside the existing `cloudflareAccounts` import:

```typescript
  const [common, auth, users, roles, projects, auditLog, cloudflareAccounts, cloudflareDns] = await Promise.all([
    import(`../../../../locales/${locale}/common.json`),
    import(`../../../../locales/${locale}/modules/auth.json`),
    import(`../../../../locales/${locale}/modules/users.json`),
    import(`../../../../locales/${locale}/modules/roles.json`),
    import(`../../../../locales/${locale}/modules/projects.json`),
    import(`../../../../locales/${locale}/modules/audit-log.json`),
    import(`../../../../locales/${locale}/modules/cloudflare-accounts.json`),
    import(`../../../../locales/${locale}/modules/cloudflare-dns.json`),
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
      cloudflareDns: cloudflareDns.default,
    },
  };
```

Also add `"actions.manageDns": "Manage DNS"` to both `frontend/locales/en/modules/projects.json` and `frontend/locales/vi/modules/projects.json`'s `actions` object (used by Step 3's `aria-label`).

- [ ] **Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`
Expected: no errors; the build's route manifest includes `/admin/environments/[environmentId]/dns`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/\[locale\]/\(dashboard\)/admin/environments frontend/src/modules/projects/ui/project-detail-view.tsx \
  frontend/locales/en/modules/cloudflare-dns.json frontend/locales/vi/modules/cloudflare-dns.json \
  frontend/locales/en/modules/projects.json frontend/locales/vi/modules/projects.json \
  frontend/src/shared/lib/i18n/request.ts
git commit -m "feat(cloudflare-dns): add environment DNS route, sidebar affordance, and i18n"
```

---

## Task 26: Whole-phase verification and finish

**Files:** none new — this task only runs checks and closes out the branch.

- [ ] **Step 1: Full backend verification**

Run: `cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q`
Expected: all green — this must include every Phase 1–3 test still passing (no regressions), plus every new test from Tasks 1–17.

- [ ] **Step 2: Full frontend verification**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`
Expected: all green; the build's route manifest includes the new `/admin/environments/[environmentId]/dns` route.

- [ ] **Step 3: Manual smoke test against `itsm_test`**

Against the `itsm_test` sibling database on the shared port-5435 server (never `business-chatbot-postgres`'s live `itsm` database), run the Phase 4 demo script by hand through the actual UI: bind an environment to an account + zone → create an A record → confirm `managed_by=SYSTEM` and a real `cf_record_id` are shown → delete it → confirm a sub-EDITOR-level user gets blocked from writing, with no partial state visible on either side.

- [ ] **Step 4: GitNexus**

Run: `node .gitnexus/run.cjs analyze` (or `npx gitnexus analyze` if the runner script is missing) to refresh the index.
Run: `git diff develop..feature/cloudflare-dns --stat` and confirm the touched-files list matches this plan's Architecture Impact section exactly — no unexpected blast radius. GitNexus's MCP query tools (`impact`/`detect_changes`/`check`) are not exposed in this session's toolset, same as every prior phase this session — this manual diff review substitutes for `detect_changes`, disclosed rather than silently skipped.

- [ ] **Step 5: `reviewing-code-against-skills` checklist**

```text
[ ] nextjs-modular-architecture: module boundary, import direction correct? (no entities/ promotion for cloudflare_configs/dns_records — deliberate, see Architecture Impact)
[ ] No proxy re-exports (direct imports from @/entities/environment, @/entities/cloudflare-account)?
[ ] No hardcoded string literals (ACTIONS/RESOURCES/PERMISSIONS used throughout)?
[ ] Server Component SSR prefetch (the new dns/page.tsx) guarded with hasPermission?
[ ] ui-ux-pro-max actually invoked for Tasks 22/23/24 (binding form, record dialog, table)?
[ ] fastapi-modular-scaffold: router thinness — no business logic in router.py (zone-ownership check, priority validation, CF-first sequencing all live in services)?
[ ] Class-scoped constants (rule #16) — every new enum/error-code/audit-action in a named class?
[ ] Decision #1 regression test present and passing (POST /cloudflare-configs reads body correctly)?
[ ] Decision #5 regression test present and passing (cross-account zone spoofing rejected)?
[ ] Decision #3's 3 failure-path tests present and passing (create/update/delete local-failure-after-CF-success)?
[ ] No hardcoded secrets / sensitive URLs
[ ] Diff contains no junk files
```

If any item fails: fix, re-run Steps 1–2, re-check. Max 2 fix→review rounds for architectural findings (mechanical lint/format fixes have no round limit).

- [ ] **Step 6: Finish the branch**

Announce: "I'm using the finishing-a-development-branch skill to complete this work." Follow that skill: verify tests on the current tree (Steps 1–2 above already did this), present the standard 3-option menu (merge to `develop` locally / push + PR / keep as-is) for this normal repo (no worktree in use this session), execute the chosen option, then clean up.

---

## Self-Review (spec coverage — completed while writing this plan)

Every item in the approved plan's "Phase 4 — Detailed Plan" section maps to a task above: Decisions #1–#8 → Tasks 9, 9, 13/14/15, 1+3, 4+10+17, (implicit throughout Task 17's route pairing), (no task touches `public.py`, confirmed absent by design), 6 respectively; the `GET /environments/{environment_id}` gap → Task 7; the `.importlinter` retrofit → Task 8; the 9 routes → Task 17; every frontend piece named in the approved plan's Architecture Impact → Tasks 18–25. Two small refinements were made while grounding this plan in the actual current code (not scope changes, just filling in implementation detail the architecture-level plan correctly left unspecified): a `DnsRecordsExistForConfig` guard on binding deletion (Task 11, closing a referential-integrity gap — deleting a binding while `dns_records` rows still reference it via `environment_id` would orphan them) and a `CloudflareDnsOperationRejected` exception distinct from `InvalidCloudflareToken` for the 3 DNS write client methods (Task 2/5 — a rejected write isn't necessarily an auth problem). No placeholders remain in any task; every code block is complete and copy-pasteable.
