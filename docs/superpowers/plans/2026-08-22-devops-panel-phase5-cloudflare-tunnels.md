# Phase 5 — Cloudflare Tunnel Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let environments manage Cloudflare Tunnels end-to-end — create, reveal connector token, add/edit/remove public hostnames (ingress rules), check connection status — all through the app.

**Architecture:** Extends the existing `app/modules/cloudflare/` module (no new module) with 2 new tables. Extends `app/integrations/cloudflare/client.py` with 6 new methods. First real usage of `app/integrations/cache/`'s `try_acquire_lock`/`release_lock` (built in an earlier phase, never called until now) to serialize concurrent edits to a Tunnel's ingress array, since Cloudflare's `PUT .../configurations` overwrites the whole array with no per-rule endpoint.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, httpx, Redis (via `redis.asyncio`), pytest + testcontainers (Postgres) + real Redis, Next.js App Router, TanStack Query, Zod.

**Spec:** `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md`, section "Phase 5 — Detailed Plan: Cloudflare Tunnel management" (approved — plan mode exited by explicit user instruction to proceed directly to implementation, decisions resolved directly against Phase 3/4 conventions rather than a separate pressure-test pass).

## Global Constraints

- **Decision #1**: lock acquisition is reject-immediately. `try_acquire_lock` returning `False` raises `TunnelConfigLocked` (409) right away — never poll-and-wait.
- **Decision #2**: `tunnel_public_hostnames` only persists `hostname`+`service`. Ingress-array reconstruction always starts from a fresh `GET .../configurations` response (raw Cloudflare JSON), preserving `path`/`originRequest`/anything else on rules not being touched — never rebuilt from DB rows.
- **Decision #3**: `try_acquire_lock` raising `CacheUnavailable` propagates as a loud failure — mirrors `set_json`/`get_json`'s documented convention, not `get_or_load`'s degrade-to-slow (skipping the lock during an outage would silently reintroduce the race it exists to prevent). `release_lock` runs in a `finally` block and is safe unconditionally (it already swallows `RedisError` internally).
- **Decision #4**: catch-all rule detection is `"hostname" not in rule or rule.get("hostname") is None`. The splice `[*named_rules, new_rule, *catch_all]` is correct by construction for both an empty starting `ingress: []` and a non-empty one.
- **Decision #5**: the compensating PUT-back-to-captured-`current_ingress` on local-write failure is accepted best-effort (not guaranteed byte-exact) — same disclosed-risk framing as Phase 4's `DnsRecordSyncFailed`. Logged `CRITICAL` either way, raises `TunnelIngressSyncFailed`, never silently reports success.
- **Decision #6**: reveal-tunnel-token requires only EDITOR (not OWNER) — narrow-blast-radius secret (runs one `cloudflared` daemon for one tunnel), proportionate to the trust level already required for tunnel CRUD.
- **Decision #7**: `DeleteCloudflareTunnel` does **not** guard on existing `tunnel_public_hostnames` rows (`ON DELETE CASCADE` handles it) — differs deliberately from Phase 4's `DeleteCloudflareConfig`, which does guard, because DNS records are independent zone resources and tunnel hostnames are not.
- **Decision #8**: the connector token is never persisted (no token column on `cloudflare_tunnels`). `CreateCloudflareTunnel` calls `create_tunnel` then `get_tunnel_token` and returns the plaintext token directly in the create response; a separate reveal-token endpoint re-fetches it live on demand.
- **Decision #9**: `config_src` is hardcoded to `"cloudflare"` inside `CloudflareClient.create_tunnel` — never exposed as a request field on this app's own endpoint.
- **Decision #10**: status sync is on-demand only (`POST .../refresh-status`), never automatic. `list_tunnel_connections` returning 0 connections = `DOWN`, ≥1 = `HEALTHY`; `DEGRADED` is never auto-set (no documented threshold exists); new tunnels default to `UNKNOWN`.
- Router thinness (rule #10): `router.py` only translates HTTP → use-case call. Lock handling, ingress-splice logic, and compensating actions all live in `services/`.
- Class-scoped constants (rule #16): every new enum/error-code/audit-action goes into a named class in `constants.py`.
- One environment can have **many** tunnels (1:N, unlike `cloudflare_configs`' 1:1) — `list_tunnels`/`create_tunnel` operate on a collection.
- Current Alembic head is `d7e2a4c9f1b3`. No `.importlinter` change needed — `app.integrations.cloudflare` and `app.modules.cloudflare` are already covered by existing contracts.
- All manual/smoke verification uses the `itsm_test` sibling database on the shared port-5435 Postgres server — never `business-chatbot-postgres`'s live `itsm` database.

---

## Task 1: Migration — `cloudflare_tunnels` + `tunnel_public_hostnames`

**Files:**
- Create: `backend/alembic/versions/f3a8c1d9e4b7_create_cloudflare_tunnel_schema.py`

**Interfaces:**
- Produces: tables `cloudflare_tunnels` (`id`, `environment_id` FK→`environments.id` CASCADE — **not unique**, `cf_tunnel_id` varchar(64) **UNIQUE** — added beyond the ERD's literal shorthand, same reasoning as Phase 4 making `dns_records.cf_record_id` UNIQUE, `name` varchar(255), `status` enum `healthy|degraded|down|unknown` default `unknown`, `last_synced_at` nullable, `created_at`, `updated_at`) and `tunnel_public_hostnames` (`id`, `tunnel_id` FK→`cloudflare_tunnels.id` CASCADE, `hostname` varchar(255) UNIQUE, `service` varchar(255), `managed_by` enum `system|external` default `system`, `created_by` FK→`users.id` SET NULL nullable, `last_synced_at` nullable, `created_at`, `updated_at`).

- [ ] **Step 1: Write the migration**

```python
"""create_cloudflare_tunnel_schema

Revision ID: f3a8c1d9e4b7
Revises: d7e2a4c9f1b3
Create Date: 2026-08-23 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f3a8c1d9e4b7'
down_revision = 'd7e2a4c9f1b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cloudflare_tunnels',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('environment_id', sa.UUID(), nullable=False),
    sa.Column('cf_tunnel_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column(
        'status',
        sa.Enum('healthy', 'degraded', 'down', 'unknown', name='cloudflaretunnelstatus', native_enum=False),
        nullable=False,
        server_default='unknown',
    ),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['environment_id'], ['environments.id'], name=op.f('cloudflare_tunnels_environment_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('cloudflare_tunnels_pkey')),
    sa.UniqueConstraint('cf_tunnel_id', name=op.f('cloudflare_tunnels_cf_tunnel_id_key'))
    )
    op.create_index(
        op.f('cloudflare_tunnels_environment_id_idx'), 'cloudflare_tunnels', ['environment_id'], unique=False
    )
    op.create_table('tunnel_public_hostnames',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tunnel_id', sa.UUID(), nullable=False),
    sa.Column('hostname', sa.String(length=255), nullable=False),
    sa.Column('service', sa.String(length=255), nullable=False),
    sa.Column(
        'managed_by',
        sa.Enum('system', 'external', name='tunnelhostnamemanagedby', native_enum=False),
        nullable=False,
        server_default='system',
    ),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(
        ['tunnel_id'], ['cloudflare_tunnels.id'], name=op.f('tunnel_public_hostnames_tunnel_id_fkey'),
        ondelete='CASCADE'
    ),
    sa.ForeignKeyConstraint(
        ['created_by'], ['users.id'], name=op.f('tunnel_public_hostnames_created_by_fkey'), ondelete='SET NULL'
    ),
    sa.PrimaryKeyConstraint('id', name=op.f('tunnel_public_hostnames_pkey')),
    sa.UniqueConstraint('hostname', name=op.f('tunnel_public_hostnames_hostname_key'))
    )
    op.create_index(
        op.f('tunnel_public_hostnames_tunnel_id_idx'), 'tunnel_public_hostnames', ['tunnel_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('tunnel_public_hostnames_tunnel_id_idx'), table_name='tunnel_public_hostnames')
    op.drop_table('tunnel_public_hostnames')
    op.drop_index(op.f('cloudflare_tunnels_environment_id_idx'), table_name='cloudflare_tunnels')
    op.drop_table('cloudflare_tunnels')
```

- [ ] **Step 2: Apply to `itsm_test` and verify reversibility**

Run: `cd backend && DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test alembic upgrade head`
Expected: no errors.

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: both succeed (proves reversibility).

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/f3a8c1d9e4b7_create_cloudflare_tunnel_schema.py
git commit -m "feat(cloudflare): add cloudflare_tunnels and tunnel_public_hostnames migration"
```

---

## Task 2: Constants, models, schemas, exceptions additions

**Files:**
- Modify: `backend/app/modules/cloudflare/constants.py`
- Modify: `backend/app/modules/cloudflare/models.py`
- Modify: `backend/app/modules/cloudflare/schemas.py`
- Modify: `backend/app/modules/cloudflare/exceptions.py`
- Test: `backend/tests/cloudflare/test_tunnel_schema_smoke.py`

**Interfaces:**
- Produces: `TunnelStatus(StrEnum: HEALTHY/DEGRADED/DOWN/UNKNOWN)`, `CloudflareTunnelAuditActions(StrEnum)`; ORM `CloudflareTunnel`, `TunnelPublicHostname`; schemas `CloudflareTunnelRead`, `CloudflareTunnelCreate`, `TunnelTokenResponse`, `TunnelPublicHostnameRead`, `TunnelPublicHostnameCreate`, `TunnelPublicHostnameUpdate`; exceptions `CloudflareTunnelNotFound`, `TunnelPublicHostnameNotFound`, `TunnelConfigLocked`, `TunnelHostnameAlreadyExists`, `TunnelIngressSyncFailed`. Reuses the existing `ManagedBy` enum unchanged (do not redefine).

- [ ] **Step 1: Write the failing smoke test**

Create `backend/tests/cloudflare/test_tunnel_schema_smoke.py`:

```python
"""Smoke test: every new Phase 5 symbol exists and imports cleanly."""


def test_new_symbols_import() -> None:
    from app.modules.cloudflare.constants import CloudflareTunnelAuditActions, ErrorCode, TunnelStatus
    from app.modules.cloudflare.exceptions import (
        CloudflareTunnelNotFound,
        TunnelConfigLocked,
        TunnelHostnameAlreadyExists,
        TunnelIngressSyncFailed,
        TunnelPublicHostnameNotFound,
    )
    from app.modules.cloudflare.models import CloudflareTunnel, TunnelPublicHostname
    from app.modules.cloudflare.schemas import (
        CloudflareTunnelCreate,
        CloudflareTunnelRead,
        TunnelPublicHostnameCreate,
        TunnelPublicHostnameRead,
        TunnelPublicHostnameUpdate,
        TunnelTokenResponse,
    )

    assert TunnelStatus.UNKNOWN == "unknown"
    assert TunnelStatus.HEALTHY == "healthy"
    assert ErrorCode.TUNNEL_NOT_FOUND == "cloudflare_tunnel_not_found"
    assert CloudflareTunnelAuditActions.TUNNEL_CREATED == "CLOUDFLARE_TUNNEL_CREATED"
    assert issubclass(CloudflareTunnelNotFound, Exception)
    assert issubclass(TunnelPublicHostnameNotFound, Exception)
    assert issubclass(TunnelConfigLocked, Exception)
    assert issubclass(TunnelHostnameAlreadyExists, Exception)
    assert issubclass(TunnelIngressSyncFailed, Exception)
    assert CloudflareTunnel.__tablename__ == "cloudflare_tunnels"
    assert TunnelPublicHostname.__tablename__ == "tunnel_public_hostnames"
    assert "cf_tunnel_id" in CloudflareTunnelRead.model_fields
    assert "name" in CloudflareTunnelCreate.model_fields
    assert "token" in TunnelTokenResponse.model_fields
    assert "hostname" in TunnelPublicHostnameRead.model_fields
    assert "hostname" in TunnelPublicHostnameCreate.model_fields
    assert "service" in TunnelPublicHostnameUpdate.model_fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_tunnel_schema_smoke.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add to `constants.py`**

Append to `backend/app/modules/cloudflare/constants.py`:

```python
class TunnelStatus(StrEnum):
    """Connection health of a Cloudflare Tunnel, synced on demand from
    GET .../connections (Decision #10) — DEGRADED is never auto-set, no
    documented threshold exists for it."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class CloudflareTunnelAuditActions(StrEnum):
    """Action identifiers this phase writes via audit.log_event."""

    TUNNEL_CREATED = "CLOUDFLARE_TUNNEL_CREATED"
    TUNNEL_DELETED = "CLOUDFLARE_TUNNEL_DELETED"
    TUNNEL_TOKEN_REVEALED = "CLOUDFLARE_TUNNEL_TOKEN_REVEALED"
    TUNNEL_HOSTNAME_CREATED = "CLOUDFLARE_TUNNEL_HOSTNAME_CREATED"
    TUNNEL_HOSTNAME_UPDATED = "CLOUDFLARE_TUNNEL_HOSTNAME_UPDATED"
    TUNNEL_HOSTNAME_DELETED = "CLOUDFLARE_TUNNEL_HOSTNAME_DELETED"
```

Extend the existing `ErrorCode(StrEnum)` class with:

```python
    TUNNEL_NOT_FOUND = "cloudflare_tunnel_not_found"
    TUNNEL_HOSTNAME_NOT_FOUND = "cloudflare_tunnel_hostname_not_found"
    TUNNEL_CONFIG_LOCKED = "cloudflare_tunnel_config_locked"
    TUNNEL_HOSTNAME_ALREADY_EXISTS = "cloudflare_tunnel_hostname_already_exists"
    TUNNEL_INGRESS_SYNC_FAILED = "cloudflare_tunnel_ingress_sync_failed"
```

- [ ] **Step 4: Add to `models.py`**

Append to `backend/app/modules/cloudflare/models.py` (add `TunnelStatus` to the existing constants import):

```python
class CloudflareTunnel(Base):
    """A Cloudflare Tunnel bound to an environment. One environment may have
    many tunnels (1:N, unlike CloudflareConfig's 1:1 binding)."""

    __tablename__ = "cloudflare_tunnels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    cf_tunnel_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[TunnelStatus] = mapped_column(Enum(TunnelStatus, native_enum=False), default=TunnelStatus.UNKNOWN)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TunnelPublicHostname(Base):
    """One public hostname (ingress rule) published through a Tunnel. Only
    hostname+service are persisted (Decision #2) — path/originRequest live
    only in Cloudflare's own ingress array, never modeled here."""

    __tablename__ = "tunnel_public_hostnames"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tunnel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cloudflare_tunnels.id", ondelete="CASCADE"), index=True
    )
    hostname: Mapped[str] = mapped_column(String(255), unique=True)
    service: Mapped[str] = mapped_column(String(255))
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

- [ ] **Step 5: Add to `schemas.py`**

Append to `backend/app/modules/cloudflare/schemas.py` (add `TunnelStatus` to the existing constants import):

```python
class CloudflareTunnelRead(FrozenModel):
    """One Cloudflare Tunnel."""

    id: UUID
    environment_id: UUID
    cf_tunnel_id: str
    name: str
    status: TunnelStatus
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CloudflareTunnelCreate(CustomModel):
    """Request body for POST .../cloudflare-tunnels. No config_src field —
    it's hardcoded to "cloudflare" inside the client (Decision #9)."""

    name: str


class TunnelTokenResponse(FrozenModel):
    """Response body for the create and reveal-token endpoints. Never cached
    or persisted anywhere (Decision #8)."""

    token: str


class TunnelPublicHostnameRead(FrozenModel):
    """One public hostname published through a Tunnel."""

    id: UUID
    tunnel_id: UUID
    hostname: str
    service: str
    managed_by: ManagedBy
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TunnelPublicHostnameCreate(CustomModel):
    """Request body for POST .../hostnames."""

    hostname: str
    service: str


class TunnelPublicHostnameUpdate(CustomModel):
    """Request body for PATCH .../hostnames/{id}. hostname is immutable —
    changing it means delete+recreate, mirrors DnsRecordUpdate's record_type
    immutability."""

    service: str
```

- [ ] **Step 6: Add to `exceptions.py`**

Append to `backend/app/modules/cloudflare/exceptions.py`:

```python
class CloudflareTunnelNotFound(NotFoundError):
    """Raised when no cloudflare_tunnels row matches the requested id for this environment."""

    code = ErrorCode.TUNNEL_NOT_FOUND
    message = "Cloudflare Tunnel not found"


class TunnelPublicHostnameNotFound(NotFoundError):
    """Raised when no tunnel_public_hostnames row matches the requested id for this tunnel."""

    code = ErrorCode.TUNNEL_HOSTNAME_NOT_FOUND
    message = "Tunnel public hostname not found"


class TunnelConfigLocked(ConflictError):
    """Raised when another request already holds the per-tunnel ingress lock
    (Decision #1 — reject immediately, never poll-and-wait)."""

    code = ErrorCode.TUNNEL_CONFIG_LOCKED
    message = "Another request is currently editing this tunnel's configuration — try again shortly"


class TunnelHostnameAlreadyExists(ConflictError):
    """Raised when the submitted hostname already exists in the tunnel's ingress array."""

    code = ErrorCode.TUNNEL_HOSTNAME_ALREADY_EXISTS
    message = "This hostname is already published on this tunnel"


class TunnelIngressSyncFailed(IntegrationError):
    """Raised when Cloudflare's side of an ingress PUT succeeded but the
    local Postgres write then failed. Decision #5: a compensating PUT-back
    is attempted first; this must never degrade silently."""

    code = ErrorCode.TUNNEL_INGRESS_SYNC_FAILED
    message = "Cloudflare was updated but the local record failed to save — check logs for details"
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_tunnel_schema_smoke.py -v`
Expected: PASS

- [ ] **Step 8: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/constants.py app/modules/cloudflare/models.py \
  app/modules/cloudflare/schemas.py app/modules/cloudflare/exceptions.py tests/cloudflare/test_tunnel_schema_smoke.py
ruff check app/modules/cloudflare/constants.py app/modules/cloudflare/models.py \
  app/modules/cloudflare/schemas.py app/modules/cloudflare/exceptions.py tests/cloudflare/test_tunnel_schema_smoke.py
git add app/modules/cloudflare/constants.py app/modules/cloudflare/models.py \
  app/modules/cloudflare/schemas.py app/modules/cloudflare/exceptions.py tests/cloudflare/test_tunnel_schema_smoke.py
git commit -m "feat(cloudflare): add Tunnel constants, models, schemas, exceptions"
```

---

## Task 3: 6 new `CloudflareClient` integration methods

**Files:**
- Modify: `backend/app/integrations/cloudflare/client.py`
- Test: `backend/tests/integrations/cloudflare/test_client.py`

**Interfaces:**
- Consumes: `CloudflareClient._write(path, method, api_token, *, json=None) -> dict` (existing `@helper`, already checks the v4 envelope).
- Produces: `create_tunnel(*, cf_account_id, api_token, name) -> str`, `get_tunnel_token(*, cf_account_id, cf_tunnel_id, api_token) -> str`, `list_tunnel_connections(*, cf_account_id, cf_tunnel_id, api_token) -> list[dict]`, `get_tunnel_configuration(*, cf_account_id, cf_tunnel_id, api_token) -> list[dict]`, `put_tunnel_configuration(*, cf_account_id, cf_tunnel_id, api_token, ingress: list[dict]) -> None`, `delete_tunnel(*, cf_account_id, cf_tunnel_id, api_token) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integrations/cloudflare/test_client.py`:

```python
class TestTunnelMethods:
    async def test_create_tunnel_returns_id_and_hardcodes_config_src(self, respx_mock) -> None:
        route = respx_mock.post("https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel").mock(
            return_value=httpx.Response(200, json={"success": True, "result": {"id": "tun-1"}})
        )
        client = CloudflareClient()
        tunnel_id = await client.create_tunnel(cf_account_id="acc-1", api_token="tok", name="my-tunnel")
        assert tunnel_id == "tun-1"
        assert route.calls.last.request.content
        body = json.loads(route.calls.last.request.content)
        assert body["config_src"] == "cloudflare"
        assert body["name"] == "my-tunnel"

    async def test_create_tunnel_raises_on_rejection(self, respx_mock) -> None:
        respx_mock.post("https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel").mock(
            return_value=httpx.Response(400, json={"success": False, "errors": [{"message": "bad"}]})
        )
        client = CloudflareClient()
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.create_tunnel(cf_account_id="acc-1", api_token="tok", name="my-tunnel")

    async def test_create_tunnel_raises_unavailable_on_transport_error(self, respx_mock) -> None:
        respx_mock.post("https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel").mock(
            side_effect=httpx.ConnectError("boom")
        )
        client = CloudflareClient()
        with pytest.raises(CloudflareApiUnavailable):
            await client.create_tunnel(cf_account_id="acc-1", api_token="tok", name="my-tunnel")

    async def test_get_tunnel_token_returns_plaintext(self, respx_mock) -> None:
        respx_mock.get(
            "https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel/tun-1/token"
        ).mock(return_value=httpx.Response(200, json={"success": True, "result": "eyJ0..."}))
        client = CloudflareClient()
        token = await client.get_tunnel_token(cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok")
        assert token == "eyJ0..."

    async def test_list_tunnel_connections_returns_raw_list(self, respx_mock) -> None:
        respx_mock.get(
            "https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel/tun-1/connections"
        ).mock(return_value=httpx.Response(200, json={"success": True, "result": [{"id": "conn-1"}]}))
        client = CloudflareClient()
        connections = await client.list_tunnel_connections(
            cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok"
        )
        assert connections == [{"id": "conn-1"}]

    async def test_list_tunnel_connections_empty_when_down(self, respx_mock) -> None:
        respx_mock.get(
            "https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel/tun-1/connections"
        ).mock(return_value=httpx.Response(200, json={"success": True, "result": []}))
        client = CloudflareClient()
        connections = await client.list_tunnel_connections(
            cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok"
        )
        assert connections == []

    async def test_get_tunnel_configuration_returns_ingress_array(self, respx_mock) -> None:
        respx_mock.get(
            "https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel/tun-1/configurations"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {"config": {"ingress": [{"hostname": "a.example.com", "service": "http://x"}]}},
                },
            )
        )
        client = CloudflareClient()
        ingress = await client.get_tunnel_configuration(
            cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok"
        )
        assert ingress == [{"hostname": "a.example.com", "service": "http://x"}]

    async def test_put_tunnel_configuration_sends_ingress_array(self, respx_mock) -> None:
        route = respx_mock.put(
            "https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel/tun-1/configurations"
        ).mock(return_value=httpx.Response(200, json={"success": True, "result": {}}))
        client = CloudflareClient()
        await client.put_tunnel_configuration(
            cf_account_id="acc-1",
            cf_tunnel_id="tun-1",
            api_token="tok",
            ingress=[{"hostname": "a.example.com", "service": "http://x"}, {"service": "http_status:404"}],
        )
        body = json.loads(route.calls.last.request.content)
        assert body["config"]["ingress"][0]["hostname"] == "a.example.com"
        assert body["config"]["ingress"][-1] == {"service": "http_status:404"}

    async def test_put_tunnel_configuration_raises_on_rejection(self, respx_mock) -> None:
        respx_mock.put(
            "https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel/tun-1/configurations"
        ).mock(return_value=httpx.Response(400, json={"success": False, "errors": [{"message": "bad"}]}))
        client = CloudflareClient()
        with pytest.raises(CloudflareDnsOperationRejected):
            await client.put_tunnel_configuration(
                cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok", ingress=[]
            )

    async def test_delete_tunnel_succeeds(self, respx_mock) -> None:
        route = respx_mock.delete(
            "https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel/tun-1"
        ).mock(return_value=httpx.Response(200, json={"success": True, "result": {}}))
        client = CloudflareClient()
        await client.delete_tunnel(cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok")
        assert route.called

    async def test_delete_tunnel_raises_unavailable_on_5xx(self, respx_mock) -> None:
        respx_mock.delete(
            "https://api.cloudflare.com/client/v4/accounts/acc-1/cfd_tunnel/tun-1"
        ).mock(return_value=httpx.Response(500, json={"success": False}))
        client = CloudflareClient()
        with pytest.raises(CloudflareApiUnavailable):
            await client.delete_tunnel(cf_account_id="acc-1", cf_tunnel_id="tun-1", api_token="tok")
```

Add `import json` to the top of the test file if not already present (check first — the existing DNS tests likely already import it for payload assertions; if so, skip this).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integrations/cloudflare/test_client.py -k Tunnel -v`
Expected: FAIL with `AttributeError: 'CloudflareClient' object has no attribute 'create_tunnel'`.

- [ ] **Step 3: Implement the 6 methods**

Append to `backend/app/integrations/cloudflare/client.py` (inside the `CloudflareClient` class, after `delete_dns_record`):

```python
    @integration
    async def create_tunnel(self, *, cf_account_id: str, api_token: str, name: str) -> str:
        """POST /accounts/{cf_account_id}/cfd_tunnel. config_src is hardcoded
        to "cloudflare" (Decision #9) — never a caller-supplied field, since
        this app must control ingress via the API, and Cloudflare's own
        reference calls "cloudflare" mandatory for that. Returns cf_tunnel_id."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel",
            "POST",
            api_token,
            json={"name": name, "config_src": "cloudflare"},
        )
        return body["result"]["id"]

    @integration
    async def get_tunnel_token(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> str:
        """GET /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/token. Never
        cached or persisted by any caller (Decision #8) — fetched live every time."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/token", "GET", api_token
        )
        return body["result"]

    @integration
    async def list_tunnel_connections(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str
    ) -> list[dict]:
        """GET /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/connections.
        Caller only needs len() of the result — 0 connections means DOWN."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/connections", "GET", api_token
        )
        return body["result"]

    @integration
    async def get_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str
    ) -> list[dict]:
        """GET /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations.
        Returns the raw ingress array — Decision #2: this is the only source
        of truth for fields this app doesn't model (path, originRequest)."""
        body = await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations", "GET", api_token
        )
        return body["result"].get("config", {}).get("ingress", [])

    @integration
    async def put_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str, ingress: list[dict]
    ) -> None:
        """PUT /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations.
        Overwrites the ENTIRE ingress array — no per-rule endpoint exists.
        Caller must have already reconstructed the full array (Decision #2)."""
        await self._write(
            f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}/configurations",
            "PUT",
            api_token,
            json={"config": {"ingress": ingress}},
        )

    @integration
    async def delete_tunnel(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> None:
        """DELETE /accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}."""
        await self._write(f"/accounts/{cf_account_id}/cfd_tunnel/{cf_tunnel_id}", "DELETE", api_token)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integrations/cloudflare/test_client.py -k Tunnel -v`
Expected: PASS (11/11)

- [ ] **Step 5: Lint, format, commit**

```bash
cd backend && ruff format app/integrations/cloudflare/client.py tests/integrations/cloudflare/test_client.py
ruff check app/integrations/cloudflare/client.py tests/integrations/cloudflare/test_client.py
git add app/integrations/cloudflare/client.py tests/integrations/cloudflare/test_client.py
git commit -m "feat(cloudflare): add 6 Tunnel methods to CloudflareClient"
```

---

## Task 4: Repository/UoW additions for tunnels + hostnames

**Files:**
- Modify: `backend/app/modules/cloudflare/repository.py`
- Modify: `backend/app/modules/cloudflare/uow.py`
- Test: `backend/tests/cloudflare/test_repository.py`

**Interfaces:**
- Produces: `AbstractCloudflareTunnelRepository`/`CloudflareTunnelRepository` (`get_by_id`, `list_page`, `list_for_environment(environment_id) -> list[CloudflareTunnelRead]`, `create(*, environment_id, cf_tunnel_id, name) -> CloudflareTunnelRead`, `update_status(tunnel_id, *, status, last_synced_at) -> CloudflareTunnelRead`, `delete(tunnel_id) -> None`); `AbstractTunnelHostnameRepository`/`TunnelHostnameRepository` (`get_by_id`, `list_page`, `list_for_tunnel(tunnel_id) -> list[TunnelPublicHostnameRead]`, `create(*, tunnel_id, hostname, service, created_by) -> TunnelPublicHostnameRead`, `update_service(hostname_id, *, service) -> TunnelPublicHostnameRead`, `delete(hostname_id) -> None`). Both wired into `AbstractCloudflareUnitOfWork` as `.tunnels`/`.tunnel_hostnames`.

- [ ] **Step 1: Write the failing test**

`test_repository.py` already has a `_session` fixture (one `AsyncSession` per test, backed by the shared session-scoped `engine`, with FK-ordered teardown deletes) and a `_make_environment(session) -> Environment` helper (creates a throwaway `Project` + `Environment` row) — both used by `TestCloudflareConfigRepository`/`TestDnsRecordRepository` already. Reuse them as-is. Append to `backend/tests/cloudflare/test_repository.py`:

```python
class TestCloudflareTunnelRepository:
    async def test_create_and_get_by_id(self, _session) -> None:
        environment_id = await _make_environment(_session)
        repo = CloudflareTunnelRepository(_session)
        created = await repo.create(environment_id=environment_id, cf_tunnel_id="tun-1", name="prod-tunnel")
        assert created.status == "unknown"
        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.cf_tunnel_id == "tun-1"

    async def test_list_for_environment_supports_many_tunnels(self, _session) -> None:
        environment_id = await _make_environment(_session)
        repo = CloudflareTunnelRepository(_session)
        await repo.create(environment_id=environment_id, cf_tunnel_id="tun-a", name="a")
        await repo.create(environment_id=environment_id, cf_tunnel_id="tun-b", name="b")
        tunnels = await repo.list_for_environment(environment_id)
        assert len(tunnels) == 2

    async def test_update_status(self, _session) -> None:
        environment_id = await _make_environment(_session)
        repo = CloudflareTunnelRepository(_session)
        created = await repo.create(environment_id=environment_id, cf_tunnel_id="tun-1", name="prod-tunnel")
        updated = await repo.update_status(created.id, status="healthy", last_synced_at=datetime.now(UTC))
        assert updated.status == "healthy"
        assert updated.last_synced_at is not None

    async def test_delete(self, _session) -> None:
        environment_id = await _make_environment(_session)
        repo = CloudflareTunnelRepository(_session)
        created = await repo.create(environment_id=environment_id, cf_tunnel_id="tun-1", name="prod-tunnel")
        await repo.delete(created.id)
        assert await repo.get_by_id(created.id) is None


class TestTunnelHostnameRepository:
    async def test_create_and_list_for_tunnel(self, _session) -> None:
        environment_id = await _make_environment(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            environment_id=environment_id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        created = await repo.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://localhost:8080", created_by=None
        )
        assert created.managed_by == "system"
        hostnames = await repo.list_for_tunnel(tunnel.id)
        assert len(hostnames) == 1
        assert hostnames[0].hostname == "app.example.com"

    async def test_update_service(self, _session) -> None:
        environment_id = await _make_environment(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            environment_id=environment_id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        created = await repo.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://localhost:8080", created_by=None
        )
        updated = await repo.update_service(created.id, service="http://localhost:9090")
        assert updated.service == "http://localhost:9090"

    async def test_delete(self, _session) -> None:
        environment_id = await _make_environment(_session)
        tunnel = await CloudflareTunnelRepository(_session).create(
            environment_id=environment_id, cf_tunnel_id="tun-1", name="prod-tunnel"
        )
        repo = TunnelHostnameRepository(_session)
        created = await repo.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://localhost:8080", created_by=None
        )
        await repo.delete(created.id)
        assert await repo.get_by_id(created.id) is None
```

Add `from datetime import UTC, datetime` and `from app.modules.cloudflare.repository import CloudflareTunnelRepository, TunnelHostnameRepository` to the test file's existing imports (extend the block already there — do not duplicate).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_repository.py -k "Tunnel" -v`
Expected: FAIL with `ImportError: cannot import name 'CloudflareTunnelRepository'`.

- [ ] **Step 3: Implement the repositories**

Append to `backend/app/modules/cloudflare/repository.py` (add `TunnelStatus` to the existing `from app.modules.cloudflare.constants import (...)` line, and `CloudflareTunnel, TunnelPublicHostname` to the existing `from app.modules.cloudflare.models import (...)` line, and `CloudflareTunnelRead, TunnelPublicHostnameRead` to the existing `from app.modules.cloudflare.schemas import (...)` line):

```python
class AbstractCloudflareTunnelRepository(AbstractRepository[CloudflareTunnelRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_environment(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        """Return every tunnel for an environment — one environment may have MANY (1:N)."""
        raise NotImplementedError

    @abstractmethod
    async def create(self, *, environment_id: UUID, cf_tunnel_id: str, name: str) -> CloudflareTunnelRead:
        """Create a new tunnel row, status defaults to UNKNOWN."""
        raise NotImplementedError

    @abstractmethod
    async def update_status(
        self, tunnel_id: UUID, *, status: TunnelStatus, last_synced_at: datetime
    ) -> CloudflareTunnelRead:
        """Persist a fresh status reading from refresh-status."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, tunnel_id: UUID) -> None:
        """Delete a tunnel. tunnel_public_hostnames rows cascade at the DB level."""
        raise NotImplementedError


class CloudflareTunnelRepository(AbstractCloudflareTunnelRepository):
    """SQLAlchemy implementation. No cache-aside — Decision #8's reasoning
    (low-traffic, frequently-mutated) applies here identically."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> CloudflareTunnelRead | None:
        row = await self._session.get(CloudflareTunnel, entity_id)
        return CloudflareTunnelRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareTunnelRead], int]:
        """Required by AbstractRepository; tunnels are listed per-environment in practice."""
        rows = await self._session.scalars(
            select(CloudflareTunnel).order_by(CloudflareTunnel.id).limit(limit).offset(offset)
        )
        items = [CloudflareTunnelRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(CloudflareTunnel))
        return items, total or 0

    @database
    async def list_for_environment(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        rows = await self._session.scalars(
            select(CloudflareTunnel)
            .where(CloudflareTunnel.environment_id == environment_id)
            .order_by(CloudflareTunnel.created_at)
        )
        return [CloudflareTunnelRead.model_validate(row) for row in rows]

    @database
    async def create(self, *, environment_id: UUID, cf_tunnel_id: str, name: str) -> CloudflareTunnelRead:
        row = CloudflareTunnel(environment_id=environment_id, cf_tunnel_id=cf_tunnel_id, name=name)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareTunnelRead.model_validate(row)

    @database
    async def update_status(
        self, tunnel_id: UUID, *, status: TunnelStatus, last_synced_at: datetime
    ) -> CloudflareTunnelRead:
        row = await self._session.get(CloudflareTunnel, tunnel_id)
        if row is None:
            raise ValueError(f"cloudflare tunnel {tunnel_id} does not exist")
        row.status = status
        row.last_synced_at = last_synced_at
        await self._session.flush()
        await self._session.refresh(row)
        return CloudflareTunnelRead.model_validate(row)

    @database
    async def delete(self, tunnel_id: UUID) -> None:
        row = await self._session.get(CloudflareTunnel, tunnel_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


class AbstractTunnelHostnameRepository(AbstractRepository[TunnelPublicHostnameRead, UUID]):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def list_for_tunnel(self, tunnel_id: UUID) -> list[TunnelPublicHostnameRead]:
        """Return every hostname published through a tunnel."""
        raise NotImplementedError

    @abstractmethod
    async def create(
        self, *, tunnel_id: UUID, hostname: str, service: str, created_by: UUID | None
    ) -> TunnelPublicHostnameRead:
        """Create a new hostname row. Caller must have already confirmed the
        Cloudflare ingress PUT succeeded."""
        raise NotImplementedError

    @abstractmethod
    async def update_service(self, hostname_id: UUID, *, service: str) -> TunnelPublicHostnameRead:
        """Update a hostname's service target. hostname itself is immutable."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, hostname_id: UUID) -> None:
        """Delete a hostname row."""
        raise NotImplementedError


class TunnelHostnameRepository(AbstractTunnelHostnameRepository):
    """SQLAlchemy implementation. No cache-aside — Decision #8."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_id(self, entity_id: UUID) -> TunnelPublicHostnameRead | None:
        row = await self._session.get(TunnelPublicHostname, entity_id)
        return TunnelPublicHostnameRead.model_validate(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[TunnelPublicHostnameRead], int]:
        """Required by AbstractRepository; hostnames are listed per-tunnel in practice."""
        rows = await self._session.scalars(
            select(TunnelPublicHostname).order_by(TunnelPublicHostname.id).limit(limit).offset(offset)
        )
        items = [TunnelPublicHostnameRead.model_validate(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(TunnelPublicHostname))
        return items, total or 0

    @database
    async def list_for_tunnel(self, tunnel_id: UUID) -> list[TunnelPublicHostnameRead]:
        rows = await self._session.scalars(
            select(TunnelPublicHostname)
            .where(TunnelPublicHostname.tunnel_id == tunnel_id)
            .order_by(TunnelPublicHostname.created_at)
        )
        return [TunnelPublicHostnameRead.model_validate(row) for row in rows]

    @database
    async def create(
        self, *, tunnel_id: UUID, hostname: str, service: str, created_by: UUID | None
    ) -> TunnelPublicHostnameRead:
        row = TunnelPublicHostname(
            tunnel_id=tunnel_id,
            hostname=hostname,
            service=service,
            managed_by=ManagedBy.SYSTEM,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return TunnelPublicHostnameRead.model_validate(row)

    @database
    async def update_service(self, hostname_id: UUID, *, service: str) -> TunnelPublicHostnameRead:
        row = await self._session.get(TunnelPublicHostname, hostname_id)
        if row is None:
            raise ValueError(f"tunnel hostname {hostname_id} does not exist")
        row.service = service
        await self._session.flush()
        await self._session.refresh(row)
        return TunnelPublicHostnameRead.model_validate(row)

    @database
    async def delete(self, hostname_id: UUID) -> None:
        row = await self._session.get(TunnelPublicHostname, hostname_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
```

Add `from datetime import datetime` to `repository.py`'s existing imports if not already present (check — the file already imports `datetime` for `CloudflareAccountManagerRow.created_at`, so this is likely already there).

- [ ] **Step 4: Wire into the UnitOfWork**

In `backend/app/modules/cloudflare/uow.py`, add `CloudflareTunnel, TunnelHostname` repos to the imports and `AbstractCloudflareUnitOfWork`/`CloudflareUnitOfWork`:

```python
from app.modules.cloudflare.repository import (
    AbstractCloudflareAccountManagerRepository,
    AbstractCloudflareAccountRepository,
    AbstractCloudflareConfigRepository,
    AbstractCloudflareTunnelRepository,
    AbstractDnsRecordRepository,
    AbstractTunnelHostnameRepository,
    CloudflareAccountManagerRepository,
    CloudflareAccountRepository,
    CloudflareConfigRepository,
    CloudflareTunnelRepository,
    DnsRecordRepository,
    TunnelHostnameRepository,
)
```

```python
class AbstractCloudflareUnitOfWork(AbstractUnitOfWork):
    accounts: AbstractCloudflareAccountRepository
    account_managers: AbstractCloudflareAccountManagerRepository
    configs: AbstractCloudflareConfigRepository
    dns_records: AbstractDnsRecordRepository
    tunnels: AbstractCloudflareTunnelRepository
    tunnel_hostnames: AbstractTunnelHostnameRepository
    ...
```

And in `CloudflareUnitOfWork.__init__`, after the existing `self.dns_records = DnsRecordRepository(session)` line:

```python
        self.tunnels = CloudflareTunnelRepository(session)
        self.tunnel_hostnames = TunnelHostnameRepository(session)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_repository.py -k "Tunnel" -v`
Expected: PASS (7/7)

- [ ] **Step 6: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/repository.py app/modules/cloudflare/uow.py tests/cloudflare/test_repository.py
ruff check app/modules/cloudflare/repository.py app/modules/cloudflare/uow.py tests/cloudflare/test_repository.py
git add app/modules/cloudflare/repository.py app/modules/cloudflare/uow.py tests/cloudflare/test_repository.py
git commit -m "feat(cloudflare): add Tunnel and TunnelHostname repositories"
```

---

## Task 5: First-ever tests for `try_acquire_lock`/`release_lock`

**Files:**
- Test: `backend/tests/integrations/cache/test_lock.py` (new file — check whether `backend/tests/integrations/cache/` already exists; if not, create it with an empty `__init__.py` only if the repo's other `tests/integrations/*` dirs use one — check `tests/integrations/cloudflare/` first for the convention).

**Interfaces:**
- Consumes: `CacheClient.try_acquire_lock(key: str, *, ttl: int) -> bool`, `CacheClient.release_lock(key: str) -> None`, `CacheUnavailable` (all already implemented in `app/integrations/cache/client.py`/`exceptions.py`, zero existing call sites or tests anywhere in the repo — this task is their first real exercise).

This task is pure verification of existing, already-correct code — no implementation step, only tests, since the methods already exist. Still follows red→green because the test file itself doesn't exist yet.

- [ ] **Step 1: Write the tests**

Create `backend/tests/integrations/cache/test_lock.py`:

```python
"""First-ever tests of CacheClient.try_acquire_lock/release_lock — these
methods have existed since an earlier phase but had zero call sites or
tests until Phase 5's Tunnel ingress-array locking became their first
real usage."""

import asyncio

import pytest

from app.integrations.cache.client import CacheClient


class TestTryAcquireLock:
    async def test_first_caller_acquires(self, cache_client: CacheClient) -> None:
        acquired = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        assert acquired is True

    async def test_second_caller_is_rejected_while_held(self, cache_client: CacheClient) -> None:
        first = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        second = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        assert first is True
        assert second is False

    async def test_release_then_reacquire_succeeds(self, cache_client: CacheClient) -> None:
        await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        await cache_client.release_lock("lock:tunnel:t1")
        reacquired = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        assert reacquired is True

    async def test_release_of_unheld_lock_is_a_safe_noop(self, cache_client: CacheClient) -> None:
        await cache_client.release_lock("lock:tunnel:never-held")

    async def test_expiry_releases_the_lock_automatically(self, cache_client: CacheClient) -> None:
        await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=1)
        await asyncio.sleep(1.2)
        reacquired = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        assert reacquired is True

    async def test_different_keys_do_not_contend(self, cache_client: CacheClient) -> None:
        first = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        second = await cache_client.try_acquire_lock("lock:tunnel:t2", ttl=5)
        assert first is True
        assert second is True

    async def test_concurrent_acquire_attempts_only_one_wins(self, cache_client: CacheClient) -> None:
        """Proves the lock actually serializes under real concurrency, not
        just sequential calls — two coroutines race for the same key."""
        results = await asyncio.gather(
            cache_client.try_acquire_lock("lock:tunnel:race", ttl=5),
            cache_client.try_acquire_lock("lock:tunnel:race", ttl=5),
        )
        assert sorted(results) == [False, True]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integrations/cache/test_lock.py -v`
Expected: FAIL with `fixture 'cache_client' not found` if the test file's directory needs an `__init__.py`, or a collection error if the path doesn't exist yet — create any missing `__init__.py` mirroring `tests/integrations/cloudflare/`'s structure, then re-run.

- [ ] **Step 3: Confirm passing (no production code change needed)**

Run: `cd backend && uv run pytest tests/integrations/cache/test_lock.py -v`
Expected: PASS (7/7) — `try_acquire_lock`/`release_lock` already exist and are already correct; this step only confirms it.

- [ ] **Step 4: Lint, format, commit**

```bash
cd backend && ruff format tests/integrations/cache/test_lock.py
ruff check tests/integrations/cache/test_lock.py
git add tests/integrations/cache/test_lock.py
git commit -m "test(cache): add first-ever coverage for try_acquire_lock/release_lock"
```

---

## Task 6: `CreateCloudflareTunnel` service

**Files:**
- Create: `backend/app/modules/cloudflare/services/create_tunnel.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Consumes: `CloudflareClient.create_tunnel`/`get_tunnel_token` (Task 3), `AbstractCloudflareUnitOfWork.tunnels.create` (Task 4), `AuditApi.log_event` (existing).
- Produces: `CreateCloudflareTunnel(uow, client, audit_api).execute(environment_id: UUID, name: str, *, actor: UserRead) -> tuple[CloudflareTunnelRead, str]` — the `str` is the one-time plaintext connector token (Decision #8), never persisted.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/cloudflare/test_services.py` (add `CloudflareTunnelRead, TunnelPublicHostnameRead` to the existing `from app.modules.cloudflare.schemas import (...)` block, add `TunnelStatus` to the existing constants import, and add a `FakeCloudflareTunnelRepository`/`FakeTunnelHostnameRepository` pair near the other Fake repos — mirror `FakeCloudflareAccountRepository`'s shape exactly):

```python
class FakeCloudflareTunnelRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, CloudflareTunnelRead] = {}

    async def get_by_id(self, entity_id: UUID) -> CloudflareTunnelRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[CloudflareTunnelRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_environment(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        return [t for t in self._rows.values() if t.environment_id == environment_id]

    async def create(self, *, environment_id: UUID, cf_tunnel_id: str, name: str) -> CloudflareTunnelRead:
        tunnel = CloudflareTunnelRead(
            id=uuid4(),
            environment_id=environment_id,
            cf_tunnel_id=cf_tunnel_id,
            name=name,
            status=TunnelStatus.UNKNOWN,
            last_synced_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[tunnel.id] = tunnel
        return tunnel

    async def update_status(self, tunnel_id: UUID, *, status, last_synced_at) -> CloudflareTunnelRead:
        existing = self._rows[tunnel_id]
        updated = existing.model_copy(update={"status": status, "last_synced_at": last_synced_at})
        self._rows[tunnel_id] = updated
        return updated

    async def delete(self, tunnel_id: UUID) -> None:
        self._rows.pop(tunnel_id, None)


class FakeTunnelHostnameRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, TunnelPublicHostnameRead] = {}

    async def get_by_id(self, entity_id: UUID) -> TunnelPublicHostnameRead | None:
        return self._rows.get(entity_id)

    async def list_page(self, limit: int, offset: int) -> tuple[list[TunnelPublicHostnameRead], int]:
        items = list(self._rows.values())[offset : offset + limit]
        return items, len(self._rows)

    async def list_for_tunnel(self, tunnel_id: UUID) -> list[TunnelPublicHostnameRead]:
        return [h for h in self._rows.values() if h.tunnel_id == tunnel_id]

    async def create(
        self, *, tunnel_id: UUID, hostname: str, service: str, created_by: UUID | None
    ) -> TunnelPublicHostnameRead:
        row = TunnelPublicHostnameRead(
            id=uuid4(),
            tunnel_id=tunnel_id,
            hostname=hostname,
            service=service,
            managed_by=ManagedBy.SYSTEM,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._rows[row.id] = row
        return row

    async def update_service(self, hostname_id: UUID, *, service: str) -> TunnelPublicHostnameRead:
        existing = self._rows[hostname_id]
        updated = existing.model_copy(update={"service": service})
        self._rows[hostname_id] = updated
        return updated

    async def delete(self, hostname_id: UUID) -> None:
        self._rows.pop(hostname_id, None)


class FakeCloudflareTunnelClient:
    """Fakes only the 6 Tunnel methods — the DNS methods aren't needed by
    these tests, so they're omitted rather than stubbed unused."""

    def __init__(
        self,
        create_tunnel_id: str = "tun-fake",
        token: str = "token-fake",
        connections: list | None = None,
        ingress: list | None = None,
        raises_on_put: Exception | None = None,
    ) -> None:
        self._create_tunnel_id = create_tunnel_id
        self._token = token
        self._connections = connections if connections is not None else []
        self._ingress = ingress if ingress is not None else []
        self._raises_on_put = raises_on_put
        self.deleted_tunnel_ids: list[str] = []
        self.put_calls: list[list[dict]] = []

    async def create_tunnel(self, *, cf_account_id: str, api_token: str, name: str) -> str:
        return self._create_tunnel_id

    async def get_tunnel_token(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> str:
        return self._token

    async def list_tunnel_connections(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> list:
        return self._connections

    async def get_tunnel_configuration(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> list:
        return self._ingress

    async def put_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str, ingress: list[dict]
    ) -> None:
        self.put_calls.append(ingress)
        if self._raises_on_put is not None:
            raise self._raises_on_put

    async def delete_tunnel(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> None:
        self.deleted_tunnel_ids.append(cf_tunnel_id)


class TestCreateCloudflareTunnel:
    async def test_creates_tunnel_and_returns_plaintext_token_once(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("plaintext-token", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        client = FakeCloudflareTunnelClient(create_tunnel_id="tun-1", token="conn-token-xyz")
        use_case = CreateCloudflareTunnel(uow, client, FakeAuditApi())

        tunnel, token = await use_case.execute(config.environment_id, "prod-tunnel", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))

        assert tunnel.cf_tunnel_id == "tun-1"
        assert tunnel.status == "unknown"
        assert token == "conn-token-xyz"

    async def test_raises_config_not_found_when_environment_unbound(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        use_case = CreateCloudflareTunnel(uow, FakeCloudflareTunnelClient(), FakeAuditApi())
        with pytest.raises(CloudflareConfigNotFound):
            await use_case.execute(uuid4(), "prod-tunnel", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))
```

This reuses `test_services.py`'s real existing shared scaffolding verbatim: the `FakeCloudflareUnitOfWork` class (instantiated directly as `FakeCloudflareUnitOfWork()` — not a builder function), `FakeAuditApi`, `TEST_FERNET_KEY` (the module-level 32-byte test key, injected automatically by the file's `_cloudflare_fernet_key` autouse fixture), and the `ACTOR_ID`/`ACTOR_EMAIL` module constants with the `UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)` actor-construction pattern every existing DNS service test already uses (see `TestCreateDnsRecord`/`TestUpdateDnsRecord`). Before writing this task's implementation, add two lines to `FakeCloudflareUnitOfWork.__init__` (alongside its existing `self.accounts = ...`/`self.configs = ...`/`self.dns_records = ...` assignments):

```python
        self.tunnels = FakeCloudflareTunnelRepository()
        self.tunnel_hostnames = FakeTunnelHostnameRepository()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestCreateCloudflareTunnel -v`
Expected: FAIL with `ImportError: cannot import name 'CreateCloudflareTunnel'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/modules/cloudflare/services/create_tunnel.py`:

```python
"""Create a Cloudflare Tunnel: call Cloudflare to create the tunnel, fetch
its one-time connector token, then persist the local row. Decision #8: the
token is never persisted — it's returned directly in this use case's result
and never stored anywhere; RevealCloudflareTunnelToken re-fetches it live
whenever it's needed again."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound
from app.modules.cloudflare.schemas import CloudflareTunnelRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead


class CreateCloudflareTunnel(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, name: str, *, actor: UserRead
    ) -> tuple[CloudflareTunnelRead, str]:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)

        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        if account is None:
            raise CloudflareConfigNotFound()

        cf_tunnel_id = await self._client.create_tunnel(
            cf_account_id=account.cf_account_id, api_token=plaintext, name=name
        )
        token = await self._client.get_tunnel_token(
            cf_account_id=account.cf_account_id, cf_tunnel_id=cf_tunnel_id, api_token=plaintext
        )

        tunnel = await self._uow.tunnels.create(
            environment_id=environment_id, cf_tunnel_id=cf_tunnel_id, name=name
        )
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare Tunnel '{name}' created",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return tunnel, token
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestCreateCloudflareTunnel -v`
Expected: PASS (2/2)

- [ ] **Step 5: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/services/create_tunnel.py tests/cloudflare/test_services.py
ruff check app/modules/cloudflare/services/create_tunnel.py tests/cloudflare/test_services.py
git add app/modules/cloudflare/services/create_tunnel.py tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add CreateCloudflareTunnel service"
```

---

## Task 7: `DeleteCloudflareTunnel` service

**Files:**
- Create: `backend/app/modules/cloudflare/services/delete_tunnel.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Produces: `DeleteCloudflareTunnel(uow, client, audit_api).execute(environment_id: UUID, tunnel_id: UUID, *, actor: UserRead) -> None`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/cloudflare/test_services.py`:

```python
class TestDeleteCloudflareTunnel:
    async def test_deletes_on_cloudflare_then_locally_no_hostname_guard(self) -> None:
        """Decision #7: unlike DeleteCloudflareConfig, this does NOT check for
        existing tunnel_public_hostnames rows — CASCADE handles them."""
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(environment_id=config.environment_id, cf_tunnel_id="tun-1", name="t")
        await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id, hostname="a.example.com", service="http://x", created_by=None
        )
        client = FakeCloudflareTunnelClient()
        use_case = DeleteCloudflareTunnel(uow, client, FakeAuditApi())

        await use_case.execute(config.environment_id, tunnel.id, actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))

        assert client.deleted_tunnel_ids == ["tun-1"]
        assert await uow.tunnels.get_by_id(tunnel.id) is None

    async def test_raises_not_found_for_tunnel_in_different_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        other_tunnel = await uow.tunnels.create(environment_id=uuid4(), cf_tunnel_id="tun-x", name="x")
        use_case = DeleteCloudflareTunnel(uow, FakeCloudflareTunnelClient(), FakeAuditApi())
        with pytest.raises(CloudflareTunnelNotFound):
            await use_case.execute(config.environment_id, other_tunnel.id, actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestDeleteCloudflareTunnel -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the service**

Create `backend/app/modules/cloudflare/services/delete_tunnel.py`:

```python
"""Delete a Cloudflare Tunnel: call Cloudflare first, then delete locally.
Decision #7: no guard on existing tunnel_public_hostnames rows — unlike
DeleteCloudflareConfig, ON DELETE CASCADE handles them, since a tunnel's
hostnames belong to and are meant to disappear with it (they aren't
independent zone resources the way dns_records are)."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, CloudflareTunnelNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead


class DeleteCloudflareTunnel(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, tunnel_id: UUID, *, actor: UserRead) -> None:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or tunnel.environment_id != environment_id:
            raise CloudflareTunnelNotFound()

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        if account is None:
            raise CloudflareConfigNotFound()

        await self._client.delete_tunnel(
            cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
        )

        await self._uow.tunnels.delete(tunnel_id)
        await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare Tunnel '{tunnel.name}' deleted",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestDeleteCloudflareTunnel -v`
Expected: PASS (2/2)

- [ ] **Step 5: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/services/delete_tunnel.py tests/cloudflare/test_services.py
ruff check app/modules/cloudflare/services/delete_tunnel.py tests/cloudflare/test_services.py
git add app/modules/cloudflare/services/delete_tunnel.py tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add DeleteCloudflareTunnel service"
```

---

## Task 8: `RevealCloudflareTunnelToken` + `RefreshTunnelStatus` services

**Files:**
- Create: `backend/app/modules/cloudflare/services/reveal_tunnel_token.py`
- Create: `backend/app/modules/cloudflare/services/refresh_tunnel_status.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Produces: `RevealCloudflareTunnelToken(uow, client, audit_api).execute(environment_id, tunnel_id, *, actor) -> str`; `RefreshTunnelStatus(uow, client).execute(environment_id, tunnel_id) -> CloudflareTunnelRead`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py`:

```python
class TestRevealCloudflareTunnelToken:
    async def test_refetches_token_live_never_from_storage(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(environment_id=config.environment_id, cf_tunnel_id="tun-1", name="t")
        client = FakeCloudflareTunnelClient(token="fresh-token-123")
        use_case = RevealCloudflareTunnelToken(uow, client, FakeAuditApi())

        token = await use_case.execute(config.environment_id, tunnel.id, actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))

        assert token == "fresh-token-123"


class TestRefreshTunnelStatus:
    async def test_zero_connections_is_down(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(environment_id=config.environment_id, cf_tunnel_id="tun-1", name="t")
        client = FakeCloudflareTunnelClient(connections=[])
        use_case = RefreshTunnelStatus(uow, client)

        updated = await use_case.execute(config.environment_id, tunnel.id)

        assert updated.status == "down"
        assert updated.last_synced_at is not None

    async def test_one_or_more_connections_is_healthy(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(environment_id=config.environment_id, cf_tunnel_id="tun-1", name="t")
        client = FakeCloudflareTunnelClient(connections=[{"id": "c1"}, {"id": "c2"}])
        use_case = RefreshTunnelStatus(uow, client)

        updated = await use_case.execute(config.environment_id, tunnel.id)

        assert updated.status == "healthy"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k "RevealCloudflareTunnelToken or RefreshTunnelStatus" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement both services**

Create `backend/app/modules/cloudflare/services/reveal_tunnel_token.py`:

```python
"""Reveal a Tunnel's connector token: always re-fetch live from Cloudflare,
never from storage (Decision #8 — nothing is ever persisted to reveal).
Decision #6: gated at EDITOR, not OWNER, in the router — this token only
authorizes running cloudflared for ONE tunnel, a narrower blast radius than
an account's own api_token."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, CloudflareTunnelNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead


class RevealCloudflareTunnelToken(AbstractUseCase):
    def __init__(
        self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient, audit_api: AuditApi
    ) -> None:
        self._uow = uow
        self._client = client
        self._audit_api = audit_api

    @use_case
    async def execute(self, environment_id: UUID, tunnel_id: UUID, *, actor: UserRead) -> str:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or tunnel.environment_id != environment_id:
            raise CloudflareTunnelNotFound()

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        if account is None:
            raise CloudflareConfigNotFound()

        token = await self._client.get_tunnel_token(
            cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
        )

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_TOKEN_REVEALED,
            severity=AuditSeverity.INFO,
            message=f"Cloudflare Tunnel '{tunnel.name}' connector token revealed",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return token
```

Create `backend/app/modules/cloudflare/services/refresh_tunnel_status.py`:

```python
"""Refresh a Tunnel's status on demand (Decision #10 — never automatic).
0 connections = DOWN, >=1 = HEALTHY. DEGRADED is never auto-set here — no
documented Cloudflare threshold exists for it."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import TunnelStatus
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound, CloudflareTunnelNotFound
from app.modules.cloudflare.schemas import CloudflareTunnelRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class RefreshTunnelStatus(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, environment_id: UUID, tunnel_id: UUID) -> CloudflareTunnelRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or tunnel.environment_id != environment_id:
            raise CloudflareTunnelNotFound()

        ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
        if ciphertext is None:
            raise CloudflareConfigNotFound()
        plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
        if account is None:
            raise CloudflareConfigNotFound()

        connections = await self._client.list_tunnel_connections(
            cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
        )
        status = TunnelStatus.HEALTHY if connections else TunnelStatus.DOWN

        updated = await self._uow.tunnels.update_status(
            tunnel_id, status=status, last_synced_at=datetime.now(UTC)
        )
        await self._uow.commit()
        return updated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k "RevealCloudflareTunnelToken or RefreshTunnelStatus" -v`
Expected: PASS (3/3)

- [ ] **Step 5: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/services/reveal_tunnel_token.py app/modules/cloudflare/services/refresh_tunnel_status.py tests/cloudflare/test_services.py
ruff check app/modules/cloudflare/services/reveal_tunnel_token.py app/modules/cloudflare/services/refresh_tunnel_status.py tests/cloudflare/test_services.py
git add app/modules/cloudflare/services/reveal_tunnel_token.py app/modules/cloudflare/services/refresh_tunnel_status.py tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add RevealCloudflareTunnelToken and RefreshTunnelStatus services"
```

---

## Task 9: `ListTunnels` + `ListTunnelHostnames` services

**Files:**
- Create: `backend/app/modules/cloudflare/services/list_tunnels.py`
- Create: `backend/app/modules/cloudflare/services/list_tunnel_hostnames.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Produces: `ListTunnels(uow).execute(environment_id: UUID) -> list[CloudflareTunnelRead]`; `ListTunnelHostnames(uow).execute(environment_id: UUID, tunnel_id: UUID) -> list[TunnelPublicHostnameRead]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py`:

```python
class TestListTunnels:
    async def test_returns_every_tunnel_for_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        environment_id = uuid4()
        await uow.tunnels.create(environment_id=environment_id, cf_tunnel_id="tun-a", name="a")
        await uow.tunnels.create(environment_id=environment_id, cf_tunnel_id="tun-b", name="b")
        use_case = ListTunnels(uow)
        tunnels = await use_case.execute(environment_id)
        assert len(tunnels) == 2


class TestListTunnelHostnames:
    async def test_returns_every_hostname_for_tunnel(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        environment_id = uuid4()
        tunnel = await uow.tunnels.create(environment_id=environment_id, cf_tunnel_id="tun-1", name="t")
        await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id, hostname="a.example.com", service="http://x", created_by=None
        )
        use_case = ListTunnelHostnames(uow)
        hostnames = await use_case.execute(environment_id, tunnel.id)
        assert len(hostnames) == 1

    async def test_raises_not_found_for_tunnel_in_different_environment(self) -> None:
        uow = FakeCloudflareUnitOfWork()
        tunnel = await uow.tunnels.create(environment_id=uuid4(), cf_tunnel_id="tun-1", name="t")
        use_case = ListTunnelHostnames(uow)
        with pytest.raises(CloudflareTunnelNotFound):
            await use_case.execute(uuid4(), tunnel.id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k "ListTunnels or ListTunnelHostnames" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement both services**

Create `backend/app/modules/cloudflare/services/list_tunnels.py`:

```python
"""List every tunnel for an environment. One environment may have MANY
tunnels (1:N, unlike cloudflare_configs' 1:1 binding to an account/zone)."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.schemas import CloudflareTunnelRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListTunnels(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID) -> list[CloudflareTunnelRead]:
        return await self._uow.tunnels.list_for_environment(environment_id)
```

Create `backend/app/modules/cloudflare/services/list_tunnel_hostnames.py`:

```python
"""List every public hostname published through one tunnel."""

from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.cloudflare.exceptions import CloudflareTunnelNotFound
from app.modules.cloudflare.schemas import TunnelPublicHostnameRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListTunnelHostnames(AbstractUseCase):
    def __init__(self, uow: AbstractCloudflareUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID, tunnel_id: UUID) -> list[TunnelPublicHostnameRead]:
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or tunnel.environment_id != environment_id:
            raise CloudflareTunnelNotFound()
        return await self._uow.tunnel_hostnames.list_for_tunnel(tunnel_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k "ListTunnels or ListTunnelHostnames" -v`
Expected: PASS (3/3)

- [ ] **Step 5: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/services/list_tunnels.py app/modules/cloudflare/services/list_tunnel_hostnames.py tests/cloudflare/test_services.py
ruff check app/modules/cloudflare/services/list_tunnels.py app/modules/cloudflare/services/list_tunnel_hostnames.py tests/cloudflare/test_services.py
git add app/modules/cloudflare/services/list_tunnels.py app/modules/cloudflare/services/list_tunnel_hostnames.py tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add ListTunnels and ListTunnelHostnames services"
```

---

## Task 10: `AddTunnelHostname` service (first lock-wrapped GET-modify-PUT)

**Files:**
- Modify: `backend/app/modules/cloudflare/constants.py` (add lock TTL constant)
- Create: `backend/app/modules/cloudflare/services/add_tunnel_hostname.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Consumes: `CacheClient.try_acquire_lock`/`release_lock` (Task 5), `CacheKeyBuilder.lock_key(entity, entity_id) -> str`, `CloudflareClient.get_tunnel_configuration`/`put_tunnel_configuration` (Task 3), `AbstractTunnelHostnameRepository.list_for_tunnel` (Task 4).
- Produces: `AddTunnelHostname(uow, client, cache, audit_api).execute(environment_id, tunnel_id, hostname, service, *, actor) -> TunnelPublicHostnameRead`. Rejects a hostname already published on this same tunnel with `TunnelHostnameAlreadyExists` (409) before ever calling Cloudflare — a lighter-weight, same-tunnel-scoped guard than the DB's own global `UNIQUE(hostname)` constraint (Task 1), which remains the backstop for a duplicate across two *different* tunnels (surfaces as a raw `IntegrityError` in that cross-tunnel case — an accepted, narrow gap, not handled specially here).

- [ ] **Step 1: Add the lock TTL constant**

Append to `backend/app/modules/cloudflare/constants.py`:

```python
class CloudflareTunnelLockDefaults:
    """Lock TTL for the 3 hostname-mutation services below — matches the
    master plan's `SET lock:tunnel:<id> NX PX 5000` (5 seconds)."""

    INGRESS_LOCK_TTL_SECONDS = 5
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py` (add `TunnelHostnameAlreadyExists` to the existing `from app.modules.cloudflare.exceptions import (...)` block, add `from app.integrations.cache.exceptions import CacheUnavailable`, and add a minimal `FakeCacheClient` near the other fakes):

```python
class FakeCacheClient:
    """Fakes only try_acquire_lock/release_lock — the 3 hostname-mutation
    services never call any other CacheClient method."""

    def __init__(self, start_locked: bool = False, raises: Exception | None = None) -> None:
        self._locked: set[str] = set()
        self._raises = raises
        self.released_keys: list[str] = []

    async def try_acquire_lock(self, key: str, *, ttl: int) -> bool:
        if self._raises is not None:
            raise self._raises
        if key in self._locked:
            return False
        self._locked.add(key)
        return True

    async def release_lock(self, key: str) -> None:
        self._locked.discard(key)
        self.released_keys.append(key)


class TestAddTunnelHostname:
    async def _setup(self, **client_kwargs):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(environment_id=config.environment_id, cf_tunnel_id="tun-1", name="t")
        client = FakeCloudflareTunnelClient(**client_kwargs)
        return uow, config, tunnel, client

    async def test_adds_to_empty_ingress(self) -> None:
        uow, config, tunnel, client = await self._setup(ingress=[])
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        created = await use_case.execute(
            config.environment_id, tunnel.id, "app.example.com", "http://localhost:8080", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        )

        assert created.hostname == "app.example.com"
        assert client.put_calls[-1] == [{"hostname": "app.example.com", "service": "http://localhost:8080"}]

    async def test_inserts_before_catch_all_and_preserves_its_unmodeled_fields(self) -> None:
        catch_all = {"service": "http_status:404", "originRequest": {"noTLSVerify": True}}
        uow, config, tunnel, client = await self._setup(ingress=[catch_all])
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        await use_case.execute(
            config.environment_id, tunnel.id, "app.example.com", "http://localhost:8080", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        )

        sent = client.put_calls[-1]
        assert sent[0] == {"hostname": "app.example.com", "service": "http://localhost:8080"}
        assert sent[-1] == catch_all

    async def test_preserves_unrelated_existing_rule_unmodeled_fields(self) -> None:
        existing_rule = {"hostname": "other.example.com", "service": "http://y", "path": "/api/*"}
        uow, config, tunnel, client = await self._setup(ingress=[existing_rule])
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        await use_case.execute(
            config.environment_id, tunnel.id, "app.example.com", "http://localhost:8080", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        )

        sent = client.put_calls[-1]
        assert existing_rule in sent

    async def test_duplicate_hostname_on_same_tunnel_rejected_before_calling_cloudflare(self) -> None:
        uow, config, tunnel, client = await self._setup(ingress=[])
        await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://old", created_by=None
        )
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        with pytest.raises(TunnelHostnameAlreadyExists):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.example.com", "http://new", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
            )
        assert client.put_calls == []

    async def test_lock_already_held_raises_config_locked_without_calling_cloudflare(self) -> None:
        uow, config, tunnel, client = await self._setup(ingress=[])
        cache = FakeCacheClient()
        await cache.try_acquire_lock(f"lock:tunnel:{tunnel.id}", ttl=5)
        use_case = AddTunnelHostname(uow, client, cache, FakeAuditApi())

        with pytest.raises(TunnelConfigLocked):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.example.com", "http://x", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
            )
        assert client.put_calls == []

    async def test_cache_unavailable_propagates_loudly(self) -> None:
        uow, config, tunnel, client = await self._setup(ingress=[])
        cache = FakeCacheClient(raises=CacheUnavailable())
        use_case = AddTunnelHostname(uow, client, cache, FakeAuditApi())

        with pytest.raises(CacheUnavailable):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.example.com", "http://x", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
            )

    async def test_lock_is_released_after_success(self) -> None:
        uow, config, tunnel, client = await self._setup(ingress=[])
        cache = FakeCacheClient()
        use_case = AddTunnelHostname(uow, client, cache, FakeAuditApi())

        await use_case.execute(
            config.environment_id, tunnel.id, "app.example.com", "http://x", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        )

        assert cache.released_keys == [f"lock:tunnel:{tunnel.id}"]

    async def test_local_write_failure_triggers_compensating_put_back_and_raises_sync_failed(self) -> None:
        starting_ingress = [{"service": "http_status:404"}]
        uow, config, tunnel, client = await self._setup(ingress=starting_ingress)

        class BrokenHostnameRepo:
            async def create(self, **kwargs):
                raise RuntimeError("db exploded")

        uow.tunnel_hostnames = BrokenHostnameRepo()
        use_case = AddTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        with pytest.raises(TunnelIngressSyncFailed):
            await use_case.execute(
                config.environment_id, tunnel.id, "app.example.com", "http://x", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
            )

        assert client.put_calls[0] == [
            {"hostname": "app.example.com", "service": "http://x"},
            {"service": "http_status:404"},
        ]
        assert client.put_calls[-1] == starting_ingress
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestAddTunnelHostname -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 4: Implement the service**

Create `backend/app/modules/cloudflare/services/add_tunnel_hostname.py`:

```python
"""Add a public hostname to a Tunnel's ingress array. This is a
GET-modify-PUT on a resource Cloudflare only exposes as a single
overwritable array (no per-rule endpoint), so the whole operation is
wrapped in a short Redis lock to prevent two concurrent editors from
clobbering each other (Decision #1: reject immediately, never poll-and-wait).

Decision #2: the array is always reconstructed from a FRESH GET, never from
DB rows — this is the only way to avoid silently dropping fields this app
doesn't model (path, originRequest, ...) on rules it isn't touching.

Decision #4: a rule is "catch-all" iff it has no hostname key, or that key
is None. New named rules are inserted before any catch-all rule(s)."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions, CloudflareTunnelLockDefaults
from app.modules.cloudflare.exceptions import (
    CloudflareConfigNotFound,
    CloudflareTunnelNotFound,
    TunnelConfigLocked,
    TunnelHostnameAlreadyExists,
    TunnelIngressSyncFailed,
)
from app.modules.cloudflare.schemas import TunnelPublicHostnameRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


def _is_catch_all(rule: dict) -> bool:
    return "hostname" not in rule or rule.get("hostname") is None


class AddTunnelHostname(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractCloudflareUnitOfWork,
        client: CloudflareClient,
        cache: CacheClient,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._client = client
        self._cache = cache
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, tunnel_id: UUID, hostname: str, service: str, *, actor: UserRead
    ) -> TunnelPublicHostnameRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or tunnel.environment_id != environment_id:
            raise CloudflareTunnelNotFound()
        existing_on_tunnel = await self._uow.tunnel_hostnames.list_for_tunnel(tunnel_id)
        if any(h.hostname == hostname for h in existing_on_tunnel):
            raise TunnelHostnameAlreadyExists()

        lock_key = CacheKeyBuilder.lock_key("tunnel", tunnel_id)
        acquired = await self._cache.try_acquire_lock(
            lock_key, ttl=CloudflareTunnelLockDefaults.INGRESS_LOCK_TTL_SECONDS
        )
        if not acquired:
            raise TunnelConfigLocked()

        try:
            ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
            if ciphertext is None:
                raise CloudflareConfigNotFound()
            plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
            account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
            if account is None:
                raise CloudflareConfigNotFound()

            current_ingress = await self._client.get_tunnel_configuration(
                cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
            )
            named_rules = [r for r in current_ingress if not _is_catch_all(r)]
            catch_all = [r for r in current_ingress if _is_catch_all(r)]
            new_rule = {"hostname": hostname, "service": service}
            new_ingress = [*named_rules, new_rule, *catch_all]

            await self._client.put_tunnel_configuration(
                cf_account_id=account.cf_account_id,
                cf_tunnel_id=tunnel.cf_tunnel_id,
                api_token=plaintext,
                ingress=new_ingress,
            )

            try:
                created = await self._uow.tunnel_hostnames.create(
                    tunnel_id=tunnel_id, hostname=hostname, service=service, created_by=actor.id
                )
                await self._uow.commit()
            except Exception:
                logger.critical(
                    "Local tunnel hostname write failed after Cloudflare PUT succeeded — attempting "
                    "compensating PUT-back (tunnel_id=%s, hostname=%s)",
                    tunnel_id,
                    hostname,
                )
                try:
                    await self._client.put_tunnel_configuration(
                        cf_account_id=account.cf_account_id,
                        cf_tunnel_id=tunnel.cf_tunnel_id,
                        api_token=plaintext,
                        ingress=current_ingress,
                    )
                    logger.critical("Compensating PUT-back succeeded (tunnel_id=%s)", tunnel_id)
                except Exception:
                    logger.critical(
                        "Compensating PUT-back ALSO failed — ingress may be out of sync, manual "
                        "reconciliation required (tunnel_id=%s)",
                        tunnel_id,
                    )
                raise TunnelIngressSyncFailed() from None
        finally:
            await self._cache.release_lock(lock_key)

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_HOSTNAME_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Tunnel hostname '{hostname}' added",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return created
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestAddTunnelHostname -v`
Expected: PASS (8/8)

- [ ] **Step 6: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/constants.py app/modules/cloudflare/services/add_tunnel_hostname.py tests/cloudflare/test_services.py
ruff check app/modules/cloudflare/constants.py app/modules/cloudflare/services/add_tunnel_hostname.py tests/cloudflare/test_services.py
git add app/modules/cloudflare/constants.py app/modules/cloudflare/services/add_tunnel_hostname.py tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add AddTunnelHostname service with Redis-locked ingress GET-modify-PUT"
```

---

## Task 11: `UpdateTunnelHostname` service

**Files:**
- Create: `backend/app/modules/cloudflare/services/update_tunnel_hostname.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Produces: `UpdateTunnelHostname(uow, client, cache, audit_api).execute(environment_id, tunnel_id, hostname_id, service, *, actor) -> TunnelPublicHostnameRead`. `hostname` itself is immutable (mirrors `record_type`'s immutability on DNS records) — only `service` can change.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py`:

```python
class TestUpdateTunnelHostname:
    async def _setup_with_hostname(self, existing_rule_extra: dict | None = None):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(environment_id=config.environment_id, cf_tunnel_id="tun-1", name="t")
        hostname_row = await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://old", created_by=None
        )
        rule = {"hostname": "app.example.com", "service": "http://old", **(existing_rule_extra or {})}
        client = FakeCloudflareTunnelClient(ingress=[rule])
        return uow, config, tunnel, hostname_row, client

    async def test_updates_service_preserving_unmodeled_fields(self) -> None:
        uow, config, tunnel, hostname_row, client = await self._setup_with_hostname({"path": "/api/*"})
        use_case = UpdateTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        updated = await use_case.execute(
            config.environment_id, tunnel.id, hostname_row.id, "http://new", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL)
        )

        assert updated.service == "http://new"
        sent = client.put_calls[-1]
        assert sent == [{"hostname": "app.example.com", "service": "http://new", "path": "/api/*"}]

    async def test_lock_already_held_raises_config_locked(self) -> None:
        uow, config, tunnel, hostname_row, client = await self._setup_with_hostname()
        cache = FakeCacheClient()
        await cache.try_acquire_lock(f"lock:tunnel:{tunnel.id}", ttl=5)
        use_case = UpdateTunnelHostname(uow, client, cache, FakeAuditApi())

        with pytest.raises(TunnelConfigLocked):
            await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, "http://new", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))
        assert client.put_calls == []

    async def test_local_write_failure_triggers_compensating_put_back(self) -> None:
        uow, config, tunnel, hostname_row, client = await self._setup_with_hostname()

        class BrokenHostnameRepo:
            async def update_service(self, *args, **kwargs):
                raise RuntimeError("db exploded")

        uow.tunnel_hostnames = BrokenHostnameRepo()
        use_case = UpdateTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        with pytest.raises(TunnelIngressSyncFailed):
            await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, "http://new", actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))

        assert client.put_calls[-1] == [{"hostname": "app.example.com", "service": "http://old"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestUpdateTunnelHostname -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the service**

Create `backend/app/modules/cloudflare/services/update_tunnel_hostname.py`:

```python
"""Update a Tunnel hostname's service target. Same lock + fresh-GET +
splice + compensating-PUT-back shape as AddTunnelHostname — see that
module's docstring for the full rationale (Decisions #1-#5). hostname
itself is immutable; only `service` is replaced in place, preserving every
other field already on that rule (path, originRequest, ...)."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions, CloudflareTunnelLockDefaults
from app.modules.cloudflare.exceptions import (
    CloudflareConfigNotFound,
    CloudflareTunnelNotFound,
    TunnelConfigLocked,
    TunnelIngressSyncFailed,
    TunnelPublicHostnameNotFound,
)
from app.modules.cloudflare.schemas import TunnelPublicHostnameRead
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class UpdateTunnelHostname(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractCloudflareUnitOfWork,
        client: CloudflareClient,
        cache: CacheClient,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._client = client
        self._cache = cache
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, tunnel_id: UUID, hostname_id: UUID, service: str, *, actor: UserRead
    ) -> TunnelPublicHostnameRead:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or tunnel.environment_id != environment_id:
            raise CloudflareTunnelNotFound()
        existing = await self._uow.tunnel_hostnames.get_by_id(hostname_id)
        if existing is None or existing.tunnel_id != tunnel_id:
            raise TunnelPublicHostnameNotFound()

        lock_key = CacheKeyBuilder.lock_key("tunnel", tunnel_id)
        acquired = await self._cache.try_acquire_lock(
            lock_key, ttl=CloudflareTunnelLockDefaults.INGRESS_LOCK_TTL_SECONDS
        )
        if not acquired:
            raise TunnelConfigLocked()

        try:
            ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
            if ciphertext is None:
                raise CloudflareConfigNotFound()
            plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
            account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
            if account is None:
                raise CloudflareConfigNotFound()

            current_ingress = await self._client.get_tunnel_configuration(
                cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
            )
            new_ingress = [
                {**rule, "service": service} if rule.get("hostname") == existing.hostname else rule
                for rule in current_ingress
            ]

            await self._client.put_tunnel_configuration(
                cf_account_id=account.cf_account_id,
                cf_tunnel_id=tunnel.cf_tunnel_id,
                api_token=plaintext,
                ingress=new_ingress,
            )

            try:
                updated = await self._uow.tunnel_hostnames.update_service(hostname_id, service=service)
                await self._uow.commit()
            except Exception:
                logger.critical(
                    "Local tunnel hostname update failed after Cloudflare PUT succeeded — attempting "
                    "compensating PUT-back (tunnel_id=%s, hostname_id=%s)",
                    tunnel_id,
                    hostname_id,
                )
                try:
                    await self._client.put_tunnel_configuration(
                        cf_account_id=account.cf_account_id,
                        cf_tunnel_id=tunnel.cf_tunnel_id,
                        api_token=plaintext,
                        ingress=current_ingress,
                    )
                    logger.critical("Compensating PUT-back succeeded (tunnel_id=%s)", tunnel_id)
                except Exception:
                    logger.critical(
                        "Compensating PUT-back ALSO failed — ingress may be out of sync, manual "
                        "reconciliation required (tunnel_id=%s)",
                        tunnel_id,
                    )
                raise TunnelIngressSyncFailed() from None
        finally:
            await self._cache.release_lock(lock_key)

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_HOSTNAME_UPDATED,
            severity=AuditSeverity.INFO,
            message=f"Tunnel hostname '{existing.hostname}' updated",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
        return updated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestUpdateTunnelHostname -v`
Expected: PASS (3/3)

- [ ] **Step 5: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/services/update_tunnel_hostname.py tests/cloudflare/test_services.py
ruff check app/modules/cloudflare/services/update_tunnel_hostname.py tests/cloudflare/test_services.py
git add app/modules/cloudflare/services/update_tunnel_hostname.py tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add UpdateTunnelHostname service"
```

---

## Task 12: `RemoveTunnelHostname` service

**Files:**
- Create: `backend/app/modules/cloudflare/services/remove_tunnel_hostname.py`
- Test: `backend/tests/cloudflare/test_services.py`

**Interfaces:**
- Produces: `RemoveTunnelHostname(uow, client, cache, audit_api).execute(environment_id, tunnel_id, hostname_id, *, actor) -> None`. Unlike DNS's `DeleteDnsRecord` (no compensating action possible on delete), this DOES have one — the pre-removal ingress array was captured, so a best-effort PUT-back is always possible (Decision #5 explicitly covers all 3 hostname-mutation services, not just create/update).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/cloudflare/test_services.py`:

```python
class TestRemoveTunnelHostname:
    async def _setup_with_hostname(self):
        uow = FakeCloudflareUnitOfWork()
        account = await uow.accounts.create(
            label="acc", cf_account_id="cf-1", api_token=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            created_by=None,
        )
        config = await uow.configs.create(
            environment_id=uuid4(), cloudflare_account_id=account.id, zone_id="z1", zone_name="example.com"
        )
        tunnel = await uow.tunnels.create(environment_id=config.environment_id, cf_tunnel_id="tun-1", name="t")
        hostname_row = await uow.tunnel_hostnames.create(
            tunnel_id=tunnel.id, hostname="app.example.com", service="http://x", created_by=None
        )
        catch_all = {"service": "http_status:404"}
        rule = {"hostname": "app.example.com", "service": "http://x"}
        client = FakeCloudflareTunnelClient(ingress=[rule, catch_all])
        return uow, config, tunnel, hostname_row, client, catch_all

    async def test_removes_rule_and_preserves_catch_all(self) -> None:
        uow, config, tunnel, hostname_row, client, catch_all = await self._setup_with_hostname()
        use_case = RemoveTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))

        assert client.put_calls[-1] == [catch_all]
        assert await uow.tunnel_hostnames.get_by_id(hostname_row.id) is None

    async def test_lock_already_held_raises_config_locked(self) -> None:
        uow, config, tunnel, hostname_row, client, _ = await self._setup_with_hostname()
        cache = FakeCacheClient()
        await cache.try_acquire_lock(f"lock:tunnel:{tunnel.id}", ttl=5)
        use_case = RemoveTunnelHostname(uow, client, cache, FakeAuditApi())

        with pytest.raises(TunnelConfigLocked):
            await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))
        assert client.put_calls == []

    async def test_local_delete_failure_triggers_compensating_put_back(self) -> None:
        uow, config, tunnel, hostname_row, client, catch_all = await self._setup_with_hostname()
        starting_ingress = [{"hostname": "app.example.com", "service": "http://x"}, catch_all]

        class BrokenHostnameRepo:
            async def delete(self, *args, **kwargs):
                raise RuntimeError("db exploded")

        uow.tunnel_hostnames = BrokenHostnameRepo()
        use_case = RemoveTunnelHostname(uow, client, FakeCacheClient(), FakeAuditApi())

        with pytest.raises(TunnelIngressSyncFailed):
            await use_case.execute(config.environment_id, tunnel.id, hostname_row.id, actor=UserRead.model_construct(id=ACTOR_ID, email=ACTOR_EMAIL))

        assert client.put_calls[0] == [catch_all]
        assert client.put_calls[-1] == starting_ingress
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestRemoveTunnelHostname -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the service**

Create `backend/app/modules/cloudflare/services/remove_tunnel_hostname.py`:

```python
"""Remove a public hostname from a Tunnel's ingress array. Same lock +
fresh-GET + splice shape as AddTunnelHostname — see that module's docstring.

Unlike DeleteDnsRecord (no compensating action possible once a real DNS
record is gone), a compensating PUT-back IS possible here: the pre-removal
ingress array was captured before the mutating PUT, so it can always be
best-effort restored on a subsequent local-delete failure (Decision #5).

Risk (documented, not solved here): if the removed rule was the only rule
and no catch-all exists, the resulting array would violate Cloudflare's own
minItems:1 — that PUT is rejected by Cloudflare itself (surfaces as a normal
CloudflareDnsOperationRejected, not a sync-failure, since it happens before
any local mutation), not silently accepted."""

import logging
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.core.crypto import FernetCodec
from app.integrations.cache.client import CacheClient
from app.integrations.cache.keys import CacheKeyBuilder
from app.integrations.cloudflare.client import CloudflareClient
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditActor, AuditApi
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.constants import CloudflareTunnelAuditActions, CloudflareTunnelLockDefaults
from app.modules.cloudflare.exceptions import (
    CloudflareConfigNotFound,
    CloudflareTunnelNotFound,
    TunnelConfigLocked,
    TunnelIngressSyncFailed,
    TunnelPublicHostnameNotFound,
)
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork
from app.modules.users.public import UserRead

logger = logging.getLogger(__name__)


class RemoveTunnelHostname(AbstractUseCase):
    def __init__(
        self,
        uow: AbstractCloudflareUnitOfWork,
        client: CloudflareClient,
        cache: CacheClient,
        audit_api: AuditApi,
    ) -> None:
        self._uow = uow
        self._client = client
        self._cache = cache
        self._audit_api = audit_api

    @use_case
    async def execute(
        self, environment_id: UUID, tunnel_id: UUID, hostname_id: UUID, *, actor: UserRead
    ) -> None:
        config = await self._uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()
        tunnel = await self._uow.tunnels.get_by_id(tunnel_id)
        if tunnel is None or tunnel.environment_id != environment_id:
            raise CloudflareTunnelNotFound()
        existing = await self._uow.tunnel_hostnames.get_by_id(hostname_id)
        if existing is None or existing.tunnel_id != tunnel_id:
            raise TunnelPublicHostnameNotFound()

        lock_key = CacheKeyBuilder.lock_key("tunnel", tunnel_id)
        acquired = await self._cache.try_acquire_lock(
            lock_key, ttl=CloudflareTunnelLockDefaults.INGRESS_LOCK_TTL_SECONDS
        )
        if not acquired:
            raise TunnelConfigLocked()

        try:
            ciphertext = await self._uow.accounts.get_token_ciphertext(config.cloudflare_account_id)
            if ciphertext is None:
                raise CloudflareConfigNotFound()
            plaintext = FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
            account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)
            if account is None:
                raise CloudflareConfigNotFound()

            current_ingress = await self._client.get_tunnel_configuration(
                cf_account_id=account.cf_account_id, cf_tunnel_id=tunnel.cf_tunnel_id, api_token=plaintext
            )
            new_ingress = [rule for rule in current_ingress if rule.get("hostname") != existing.hostname]

            await self._client.put_tunnel_configuration(
                cf_account_id=account.cf_account_id,
                cf_tunnel_id=tunnel.cf_tunnel_id,
                api_token=plaintext,
                ingress=new_ingress,
            )

            try:
                await self._uow.tunnel_hostnames.delete(hostname_id)
                await self._uow.commit()
            except Exception:
                logger.critical(
                    "Local tunnel hostname delete failed after Cloudflare PUT succeeded — attempting "
                    "compensating PUT-back (tunnel_id=%s, hostname_id=%s)",
                    tunnel_id,
                    hostname_id,
                )
                try:
                    await self._client.put_tunnel_configuration(
                        cf_account_id=account.cf_account_id,
                        cf_tunnel_id=tunnel.cf_tunnel_id,
                        api_token=plaintext,
                        ingress=current_ingress,
                    )
                    logger.critical("Compensating PUT-back succeeded (tunnel_id=%s)", tunnel_id)
                except Exception:
                    logger.critical(
                        "Compensating PUT-back ALSO failed — ingress may be out of sync, manual "
                        "reconciliation required (tunnel_id=%s)",
                        tunnel_id,
                    )
                raise TunnelIngressSyncFailed() from None
        finally:
            await self._cache.release_lock(lock_key)

        await self._audit_api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action=CloudflareTunnelAuditActions.TUNNEL_HOSTNAME_DELETED,
            severity=AuditSeverity.INFO,
            message=f"Tunnel hostname '{existing.hostname}' removed",
            actor=AuditActor(user_id=actor.id, email=actor.email),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py -k TestRemoveTunnelHostname -v`
Expected: PASS (3/3)

- [ ] **Step 5: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/services/remove_tunnel_hostname.py tests/cloudflare/test_services.py
ruff check app/modules/cloudflare/services/remove_tunnel_hostname.py tests/cloudflare/test_services.py
git add app/modules/cloudflare/services/remove_tunnel_hostname.py tests/cloudflare/test_services.py
git commit -m "feat(cloudflare): add RemoveTunnelHostname service"
```

---

## Task 13: Dependency providers for the 8 Tunnel services

**Files:**
- Modify: `backend/app/modules/cloudflare/dependencies.py`

**Interfaces:**
- Produces: `get_create_tunnel`, `get_delete_tunnel`, `get_reveal_tunnel_token`, `get_refresh_tunnel_status`, `get_list_tunnels`, `get_list_tunnel_hostnames`, `get_add_tunnel_hostname`, `get_update_tunnel_hostname`, `get_remove_tunnel_hostname` — all FastAPI dependency providers, mirroring the existing DNS providers' exact shape (e.g. `get_create_dns_record`).

No test for this task — dependency providers are exercised indirectly by Task 14's router tests. Not TDD-able in isolation (there's nothing to assert against a bare `Depends` wiring function beyond "the app starts"), consistent with how the DNS phase treated its own equivalent providers.

- [ ] **Step 1: Add the imports**

In `backend/app/modules/cloudflare/dependencies.py`, add to the existing import block:

```python
from app.integrations.cache.client import CacheClient
from app.integrations.cache.dependencies import get_cache
```

(These two are likely already imported for `get_uow` — check first and only add if missing.) Then add:

```python
from app.modules.cloudflare.services.add_tunnel_hostname import AddTunnelHostname
from app.modules.cloudflare.services.create_tunnel import CreateCloudflareTunnel
from app.modules.cloudflare.services.delete_tunnel import DeleteCloudflareTunnel
from app.modules.cloudflare.services.list_tunnel_hostnames import ListTunnelHostnames
from app.modules.cloudflare.services.list_tunnels import ListTunnels
from app.modules.cloudflare.services.refresh_tunnel_status import RefreshTunnelStatus
from app.modules.cloudflare.services.remove_tunnel_hostname import RemoveTunnelHostname
from app.modules.cloudflare.services.reveal_tunnel_token import RevealCloudflareTunnelToken
from app.modules.cloudflare.services.update_tunnel_hostname import UpdateTunnelHostname
```

- [ ] **Step 2: Add the 9 provider functions**

Append to the end of `backend/app/modules/cloudflare/dependencies.py`:

```python
async def get_create_tunnel(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> CreateCloudflareTunnel:
    """Provide the create-tunnel use case."""
    return CreateCloudflareTunnel(uow, client, audit_api)


async def get_delete_tunnel(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> DeleteCloudflareTunnel:
    """Provide the delete-tunnel use case."""
    return DeleteCloudflareTunnel(uow, client, audit_api)


async def get_reveal_tunnel_token(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    audit_api: AuditApi = Depends(get_audit_api),
) -> RevealCloudflareTunnelToken:
    """Provide the reveal-tunnel-token use case."""
    return RevealCloudflareTunnelToken(uow, client, audit_api)


async def get_refresh_tunnel_status(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
) -> RefreshTunnelStatus:
    """Provide the refresh-tunnel-status use case."""
    return RefreshTunnelStatus(uow, client)


async def get_list_tunnels(uow: AbstractCloudflareUnitOfWork = Depends(get_uow)) -> ListTunnels:
    """Provide the list-tunnels use case."""
    return ListTunnels(uow)


async def get_list_tunnel_hostnames(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
) -> ListTunnelHostnames:
    """Provide the list-tunnel-hostnames use case."""
    return ListTunnelHostnames(uow)


async def get_add_tunnel_hostname(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    cache: CacheClient = Depends(get_cache),
    audit_api: AuditApi = Depends(get_audit_api),
) -> AddTunnelHostname:
    """Provide the add-tunnel-hostname use case."""
    return AddTunnelHostname(uow, client, cache, audit_api)


async def get_update_tunnel_hostname(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    cache: CacheClient = Depends(get_cache),
    audit_api: AuditApi = Depends(get_audit_api),
) -> UpdateTunnelHostname:
    """Provide the update-tunnel-hostname use case."""
    return UpdateTunnelHostname(uow, client, cache, audit_api)


async def get_remove_tunnel_hostname(
    uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
    client: CloudflareClient = Depends(get_cloudflare_client),
    cache: CacheClient = Depends(get_cache),
    audit_api: AuditApi = Depends(get_audit_api),
) -> RemoveTunnelHostname:
    """Provide the remove-tunnel-hostname use case."""
    return RemoveTunnelHostname(uow, client, cache, audit_api)
```

- [ ] **Step 3: Verify the app still starts (import sanity check)**

Run: `cd backend && uv run python -c "from app.main import app; print('ok')"`
Expected: `ok` (no `ImportError`/circular-import failure).

- [ ] **Step 4: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/dependencies.py
ruff check app/modules/cloudflare/dependencies.py
git add app/modules/cloudflare/dependencies.py
git commit -m "feat(cloudflare): wire dependency providers for the 8 Tunnel services"
```

---

## Task 14: `router.py` — 9 new endpoints + router integration tests

**Files:**
- Modify: `backend/app/modules/cloudflare/router.py`
- Test: `backend/tests/cloudflare/test_router.py`

**Interfaces:**
- Produces 9 routes under `/environments/{environment_id}/cloudflare-tunnels[...]`, all pairing `require_permission("cloudflare_account", "view"|"manage")` with the existing, unchanged `require_account_access_for_environment(VIEWER|EDITOR)` — identical gating shape to every DNS route in this file.

- [ ] **Step 1: Write the failing router tests**

`test_router.py` already has a module-level `_bind_environment(client, engine, *, cf_client: FakeCloudflareClient) -> tuple[str, str, UUID]` helper (used by `TestDnsRecordFullDemoScript`): it logs in a fresh user with `manage`+`view`+`project:create`+`environment:create`+`environment:read`, creates a Cloudflare account (the login user becomes its OWNER), creates a project+environment, and binds them — returning `(environment_id, account_id, owner_id)` with `client` left authenticated as the owner. Reuse it as-is; do not re-derive a parallel version of it.

First, extend `FakeCloudflareClient.__init__` in place to accept the 2 new optional kwargs the Tunnel methods need, and add the 6 Tunnel methods to the class body (alongside the existing DNS methods):

```python
    def __init__(
        self,
        raises: Exception | None = None,
        zones: list | None = None,
        create_record_id: str = "rec-fake",
        create_tunnel_id: str = "tun-fake",
        tunnel_token: str = "token-fake",
        tunnel_connections: list | None = None,
        tunnel_ingress: list | None = None,
    ) -> None:
        self._raises = raises
        self._zones = zones or []
        self._create_record_id = create_record_id
        self._create_tunnel_id = create_tunnel_id
        self._tunnel_token = tunnel_token
        self._tunnel_connections = tunnel_connections if tunnel_connections is not None else []
        self._tunnel_ingress = tunnel_ingress if tunnel_ingress is not None else []
        self.deleted_record_ids: list[str] = []
        self.deleted_tunnel_ids: list[str] = []
        self.put_calls: list[list[dict]] = []

    async def create_tunnel(self, *, cf_account_id: str, api_token: str, name: str) -> str:
        return self._create_tunnel_id

    async def get_tunnel_token(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> str:
        return self._tunnel_token

    async def list_tunnel_connections(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> list:
        return self._tunnel_connections

    async def get_tunnel_configuration(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> list:
        return self._tunnel_ingress

    async def put_tunnel_configuration(
        self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str, ingress: list[dict]
    ) -> None:
        self.put_calls.append(ingress)
        self._tunnel_ingress = ingress

    async def delete_tunnel(self, *, cf_account_id: str, cf_tunnel_id: str, api_token: str) -> None:
        self.deleted_tunnel_ids.append(cf_tunnel_id)
```

Replace the class's existing `__init__` with the version above (it is a strict superset of the current one — every existing DNS test's constructor call still works unchanged since all new params are optional with defaults).

Then append the test class:

```python
class TestTunnelRouterFullDemoScript:
    async def test_create_reveal_token_add_hostnames_and_delete(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """The Phase 5 acceptance demo, verbatim: create a tunnel -> token
        shown once -> add 2 hostnames -> delete the tunnel."""
        cf_client = FakeCloudflareClient(tunnel_token="conn-token-xyz")
        environment_id, account_id, owner_id = await _bind_environment(client, engine, cf_client=cf_client)

        create_resp = await client.post(
            f"/api/v1/environments/{environment_id}/cloudflare-tunnels", json={"name": "prod-tunnel"}
        )
        assert create_resp.status_code == 200, create_resp.text
        body = create_resp.json()["data"]
        assert body["token"] == "conn-token-xyz"
        tunnel_id = body["tunnel"]["id"]

        reveal_resp = await client.post(f"/api/v1/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/reveal-token")
        assert reveal_resp.status_code == 200
        assert reveal_resp.json()["data"]["token"] == "conn-token-xyz"

        add_a = await client.post(
            f"/api/v1/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames",
            json={"hostname": "a.example.com", "service": "http://x"},
        )
        assert add_a.status_code == 200, add_a.text
        add_b = await client.post(
            f"/api/v1/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames",
            json={"hostname": "b.example.com", "service": "http://y"},
        )
        assert add_b.status_code == 200, add_b.text

        list_resp = await client.get(f"/api/v1/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames")
        assert len(list_resp.json()["data"]) == 2

        delete_resp = await client.delete(f"/api/v1/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}")
        assert delete_resp.status_code == 200
        assert cf_client.deleted_tunnel_ids == [cf_client._create_tunnel_id]

        del app.dependency_overrides[get_cloudflare_client]

    async def test_lock_contention_second_concurrent_add_hostname_gets_409(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        """Genuine two-request concurrency test — proves the Redis lock (not
        just sequential logic) actually serializes concurrent editors, per
        the Phase 5 demo script (Decision #1)."""
        import asyncio

        cf_client = FakeCloudflareClient()
        environment_id, account_id, owner_id = await _bind_environment(client, engine, cf_client=cf_client)
        create_resp = await client.post(
            f"/api/v1/environments/{environment_id}/cloudflare-tunnels", json={"name": "prod-tunnel"}
        )
        tunnel_id = create_resp.json()["data"]["tunnel"]["id"]

        responses = await asyncio.gather(
            client.post(
                f"/api/v1/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames",
                json={"hostname": "a.example.com", "service": "http://x"},
            ),
            client.post(
                f"/api/v1/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames",
                json={"hostname": "b.example.com", "service": "http://y"},
            ),
        )
        statuses = sorted(r.status_code for r in responses)
        assert statuses == [200, 409]

        del app.dependency_overrides[get_cloudflare_client]

    async def test_sub_editor_gets_403_on_hostname_write(self, client: AsyncClient, engine: AsyncEngine) -> None:
        """A VIEWER-level manager (Layer-2 below EDITOR) must be blocked from
        writing a hostname, mirroring TestDnsRecordFullDemoScript's own
        permission-boundary assertion for DNS records."""
        cf_client = FakeCloudflareClient()
        environment_id, account_id, owner_id = await _bind_environment(client, engine, cf_client=cf_client)
        create_resp = await client.post(
            f"/api/v1/environments/{environment_id}/cloudflare-tunnels", json={"name": "prod-tunnel"}
        )
        tunnel_id = create_resp.json()["data"]["tunnel"]["id"]

        viewer_id = await _login_with_permissions(
            client,
            engine,
            permissions=[("cloudflare_account", "manage"), ("cloudflare_account", "view")],
            email="viewer@example.com",
        )
        owner_token = JwtCodec.encode(
            {"sub": str(owner_id), "type": "access", "jti": "owner-reassign-tunnel"},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, owner_token)
        assign_resp = await client.post(
            f"/api/v1/cloudflare-accounts/{account_id}/managers",
            json={"userId": str(viewer_id), "accessLevel": "viewer"},
        )
        assert assign_resp.status_code == 200, assign_resp.text

        viewer_token = JwtCodec.encode(
            {"sub": str(viewer_id), "type": "access", "jti": "viewer-tunnel-write-attempt"},
            secret=auth_settings.JWT_SECRET,
            ttl_seconds=3600,
        )
        client.cookies.set(AuthCookies.ACCESS_TOKEN, viewer_token)

        response = await client.post(
            f"/api/v1/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames",
            json={"hostname": "a.example.com", "service": "http://x"},
        )
        assert response.status_code == 403

        del app.dependency_overrides[get_cloudflare_client]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_router.py -k TestTunnelRouterFullDemoScript -v`
Expected: FAIL (404s — routes don't exist yet).

- [ ] **Step 3: Add the response schema needed for create-tunnel**

The create-tunnel endpoint returns both the tunnel row and the one-time token — add to `backend/app/modules/cloudflare/schemas.py`:

```python
class CloudflareTunnelCreateResponse(FrozenModel):
    """Response body for POST .../cloudflare-tunnels — bundles the created
    tunnel with its one-time connector token (Decision #8: never persisted,
    shown exactly once here and again only via the reveal-token endpoint)."""

    tunnel: CloudflareTunnelRead
    token: str
```

- [ ] **Step 4: Implement the 9 routes**

Append to `backend/app/modules/cloudflare/router.py` (add the new imports for services/schemas/dependencies at the top, following the file's existing alphabetized-within-block import style):

```python
@router.get("/environments/{environment_id}/cloudflare-tunnels")
async def list_environment_tunnels(
    environment_id: UUID,
    use_case: ListTunnels = Depends(get_list_tunnels),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[list[CloudflareTunnelRead]]:
    """List every tunnel bound to an environment (1:N)."""
    tunnels = await use_case.execute(environment_id)
    return ApiResponse[list[CloudflareTunnelRead]](success=True, data=tunnels)


@router.post("/environments/{environment_id}/cloudflare-tunnels")
async def create_environment_tunnel(
    environment_id: UUID,
    body: CloudflareTunnelCreate,
    use_case: CreateCloudflareTunnel = Depends(get_create_tunnel),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[CloudflareTunnelCreateResponse]:
    """Create a tunnel and return its one-time connector token (Decision #8)."""
    tunnel, token = await use_case.execute(environment_id, body.name, actor=user)
    return ApiResponse[CloudflareTunnelCreateResponse](
        success=True, data=CloudflareTunnelCreateResponse(tunnel=tunnel, token=token)
    )


@router.delete("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}")
async def delete_environment_tunnel(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: DeleteCloudflareTunnel = Depends(get_delete_tunnel),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Delete a tunnel. Its public hostnames cascade at the DB level (Decision #7)."""
    await use_case.execute(environment_id, tunnel_id, actor=user)
    return ApiResponse[None](success=True)


@router.post("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/reveal-token")
async def reveal_environment_tunnel_token(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: RevealCloudflareTunnelToken = Depends(get_reveal_tunnel_token),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[TunnelTokenResponse]:
    """Re-fetch the connector token live. EDITOR only (Decision #6 — a
    narrower blast radius than an account's own OWNER-gated reveal-token)."""
    token = await use_case.execute(environment_id, tunnel_id, actor=user)
    return ApiResponse[TunnelTokenResponse](success=True, data=TunnelTokenResponse(token=token))


@router.post("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/refresh-status")
async def refresh_environment_tunnel_status(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: RefreshTunnelStatus = Depends(get_refresh_tunnel_status),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[CloudflareTunnelRead]:
    """On-demand status sync (Decision #10 — never automatic)."""
    tunnel = await use_case.execute(environment_id, tunnel_id)
    return ApiResponse[CloudflareTunnelRead](success=True, data=tunnel)


@router.get("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames")
async def list_environment_tunnel_hostnames(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: ListTunnelHostnames = Depends(get_list_tunnel_hostnames),
    _l1: UserRead = Depends(require_permission("cloudflare_account", "view")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[list[TunnelPublicHostnameRead]]:
    """List every public hostname published through a tunnel."""
    hostnames = await use_case.execute(environment_id, tunnel_id)
    return ApiResponse[list[TunnelPublicHostnameRead]](success=True, data=hostnames)


@router.post("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames")
async def add_environment_tunnel_hostname(
    environment_id: UUID,
    tunnel_id: UUID,
    body: TunnelPublicHostnameCreate,
    use_case: AddTunnelHostname = Depends(get_add_tunnel_hostname),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[TunnelPublicHostnameRead]:
    """Add a hostname — Redis-locked GET-modify-PUT (Decisions #1-#5). 409 if
    another edit is already in flight for this tunnel."""
    hostname = await use_case.execute(environment_id, tunnel_id, body.hostname, body.service, actor=user)
    return ApiResponse[TunnelPublicHostnameRead](success=True, data=hostname)


@router.patch("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames/{hostname_id}")
async def update_environment_tunnel_hostname(
    environment_id: UUID,
    tunnel_id: UUID,
    hostname_id: UUID,
    body: TunnelPublicHostnameUpdate,
    use_case: UpdateTunnelHostname = Depends(get_update_tunnel_hostname),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[TunnelPublicHostnameRead]:
    """Update a hostname's service target — same Redis-locked shape."""
    hostname = await use_case.execute(environment_id, tunnel_id, hostname_id, body.service, actor=user)
    return ApiResponse[TunnelPublicHostnameRead](success=True, data=hostname)


@router.delete("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}/hostnames/{hostname_id}")
async def remove_environment_tunnel_hostname(
    environment_id: UUID,
    tunnel_id: UUID,
    hostname_id: UUID,
    use_case: RemoveTunnelHostname = Depends(get_remove_tunnel_hostname),
    user: UserRead = Depends(require_permission("cloudflare_account", "manage")),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.EDITOR)),
) -> ApiResponse[None]:
    """Remove a hostname — same Redis-locked shape."""
    await use_case.execute(environment_id, tunnel_id, hostname_id, actor=user)
    return ApiResponse[None](success=True)
```

Confirm the actual route count matches 9 (noted as a counting-risk in the plan's own Architecture Impact section): `list`, `create`, `delete`, `reveal-token`, `refresh-status`, `list hostnames`, `add hostname`, `update hostname`, `remove hostname` = 9. Verify with:

Run: `cd backend && uv run python -c "from app.main import app; print(len([r for r in app.routes if 'cloudflare-tunnels' in getattr(r, 'path', '')]))"`
Expected: `9`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_router.py -k TestTunnelRouterFullDemoScript -v`
Expected: PASS (3/3)

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && uv run pytest -q`
Expected: all tests pass, including every pre-existing test (no regression).

- [ ] **Step 7: Lint, format, commit**

```bash
cd backend && ruff format app/modules/cloudflare/router.py app/modules/cloudflare/schemas.py tests/cloudflare/test_router.py
ruff check app/modules/cloudflare/router.py app/modules/cloudflare/schemas.py tests/cloudflare/test_router.py
python scripts/check_module_boundaries.py --strict
lint-imports
git add app/modules/cloudflare/router.py app/modules/cloudflare/schemas.py tests/cloudflare/test_router.py
git commit -m "feat(cloudflare): add 9 Tunnel router endpoints with lock-contention and permission tests"
```

---

## Task 15: Frontend — schema, fetchers, query-keys, `api.ts`

**Files:**
- Create: `frontend/src/modules/cloudflare-tunnels/model/schema.ts`
- Create: `frontend/src/modules/cloudflare-tunnels/api/fetchers.ts`
- Create: `frontend/src/modules/cloudflare-tunnels/api/query-keys.ts`
- Modify: `frontend/src/shared/constants/api.ts`

**Interfaces:**
- Produces: `cloudflareTunnelSchema`, `CloudflareTunnel`, `cloudflareTunnelCreateResponseSchema`, `CloudflareTunnelCreateResponse`, `tunnelPublicHostnameSchema`, `TunnelPublicHostname`; fetchers `fetchTunnels`, `createTunnel`, `deleteTunnel`, `revealTunnelToken`, `refreshTunnelStatus`, `fetchTunnelHostnames`, `addTunnelHostname`, `updateTunnelHostname`, `removeTunnelHostname`; `cloudflareTunnelsKeys.{all,list,hostnames}`; `API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.{ROOT,DETAIL,REVEAL_TOKEN,REFRESH_STATUS,HOSTNAMES,HOSTNAME_DETAIL}`. No test file — this module mirrors `modules/cloudflare-dns`'s untested fetcher/schema convention exactly (that module has none either; correctness is exercised through the UI tasks and manual smoke test).

- [ ] **Step 1: Add the `CLOUDFLARE_TUNNELS` endpoint block**

In `frontend/src/shared/constants/api.ts`, add after the existing `CLOUDFLARE_DNS` block (before the closing `},` of `ENDPOINTS`):

```typescript
    CLOUDFLARE_TUNNELS: {
      ROOT: (environmentId: string) => `/environments/${environmentId}/cloudflare-tunnels`,
      DETAIL: (environmentId: string, tunnelId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}`,
      REVEAL_TOKEN: (environmentId: string, tunnelId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}/reveal-token`,
      REFRESH_STATUS: (environmentId: string, tunnelId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}/refresh-status`,
      HOSTNAMES: (environmentId: string, tunnelId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}/hostnames`,
      HOSTNAME_DETAIL: (environmentId: string, tunnelId: string, hostnameId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}/hostnames/${hostnameId}`,
    },
```

- [ ] **Step 2: Write the schema**

Create `frontend/src/modules/cloudflare-tunnels/model/schema.ts`:

```typescript
import { z } from "zod";

export const TUNNEL_STATUSES = ["healthy", "degraded", "down", "unknown"] as const;

export const cloudflareTunnelSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  cfTunnelId: z.string(),
  name: z.string(),
  status: z.enum(TUNNEL_STATUSES),
  lastSyncedAt: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type CloudflareTunnel = z.infer<typeof cloudflareTunnelSchema>;
export type TunnelStatus = (typeof TUNNEL_STATUSES)[number];

export const cloudflareTunnelCreateResponseSchema = z.object({
  tunnel: cloudflareTunnelSchema,
  token: z.string(),
});
export type CloudflareTunnelCreateResponse = z.infer<typeof cloudflareTunnelCreateResponseSchema>;

export const tunnelTokenResponseSchema = z.object({
  token: z.string(),
});

export const tunnelPublicHostnameSchema = z.object({
  id: z.uuid(),
  tunnelId: z.uuid(),
  hostname: z.string(),
  service: z.string(),
  managedBy: z.enum(["system", "external"]),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type TunnelPublicHostname = z.infer<typeof tunnelPublicHostnameSchema>;
```

- [ ] **Step 3: Write the fetchers**

Create `frontend/src/modules/cloudflare-tunnels/api/fetchers.ts`:

```typescript
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import {
  cloudflareTunnelSchema,
  cloudflareTunnelCreateResponseSchema,
  tunnelPublicHostnameSchema,
  tunnelTokenResponseSchema,
  type CloudflareTunnel,
  type CloudflareTunnelCreateResponse,
  type TunnelPublicHostname,
} from "../model/schema";

export async function fetchTunnels(environmentId: string): Promise<CloudflareTunnel[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.ROOT(environmentId));
  return cloudflareTunnelSchema.array().parse(raw);
}

export async function createTunnel(
  environmentId: string,
  name: string,
): Promise<CloudflareTunnelCreateResponse> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.ROOT(environmentId), {
    method: "POST",
    data: { name },
  });
  return cloudflareTunnelCreateResponseSchema.parse(raw);
}

export async function deleteTunnel(environmentId: string, tunnelId: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.DETAIL(environmentId, tunnelId), {
    method: "DELETE",
  });
}

export async function revealTunnelToken(environmentId: string, tunnelId: string): Promise<string> {
  const raw = await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.REVEAL_TOKEN(environmentId, tunnelId),
    { method: "POST" },
  );
  return tunnelTokenResponseSchema.parse(raw).token;
}

export async function refreshTunnelStatus(environmentId: string, tunnelId: string): Promise<CloudflareTunnel> {
  const raw = await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.REFRESH_STATUS(environmentId, tunnelId),
    { method: "POST" },
  );
  return cloudflareTunnelSchema.parse(raw);
}

export async function fetchTunnelHostnames(
  environmentId: string,
  tunnelId: string,
): Promise<TunnelPublicHostname[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.HOSTNAMES(environmentId, tunnelId));
  return tunnelPublicHostnameSchema.array().parse(raw);
}

export async function addTunnelHostname(
  environmentId: string,
  tunnelId: string,
  data: { hostname: string; service: string },
): Promise<TunnelPublicHostname> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.HOSTNAMES(environmentId, tunnelId), {
    method: "POST",
    data,
  });
  return tunnelPublicHostnameSchema.parse(raw);
}

export async function updateTunnelHostname(
  environmentId: string,
  tunnelId: string,
  hostnameId: string,
  service: string,
): Promise<TunnelPublicHostname> {
  const raw = await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.HOSTNAME_DETAIL(environmentId, tunnelId, hostnameId),
    { method: "PATCH", data: { service } },
  );
  return tunnelPublicHostnameSchema.parse(raw);
}

export async function removeTunnelHostname(
  environmentId: string,
  tunnelId: string,
  hostnameId: string,
): Promise<void> {
  await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.HOSTNAME_DETAIL(environmentId, tunnelId, hostnameId),
    { method: "DELETE" },
  );
}
```

- [ ] **Step 4: Write the query-key factory**

Create `frontend/src/modules/cloudflare-tunnels/api/query-keys.ts`:

```typescript
/**
 * Hierarchical query key factory for the cloudflare-tunnels module.
 */
export const cloudflareTunnelsKeys = {
  all: ["cloudflare-tunnels"] as const,
  list: (environmentId: string) => [...cloudflareTunnelsKeys.all, "list", environmentId] as const,
  hostnames: (environmentId: string, tunnelId: string) =>
    [...cloudflareTunnelsKeys.all, "hostnames", environmentId, tunnelId] as const,
};
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors from these new files (pre-existing unrelated errors, if any, are out of scope).

- [ ] **Step 6: Commit**

```bash
cd frontend && git add src/modules/cloudflare-tunnels/model/schema.ts src/modules/cloudflare-tunnels/api/fetchers.ts src/modules/cloudflare-tunnels/api/query-keys.ts src/shared/constants/api.ts
git commit -m "feat(cloudflare-tunnels): add schema, fetchers, query-keys, api.ts endpoint block"
```

---

## Task 16: Frontend — query and mutation hooks

**Files:**
- Create: `frontend/src/modules/cloudflare-tunnels/hooks/use-tunnels.ts`
- Create: `frontend/src/modules/cloudflare-tunnels/hooks/use-tunnel-hostnames.ts`

**Interfaces:**
- Consumes: everything from Task 15.
- Produces: `useTunnelsQuery(environmentId)`, `useCreateTunnel(environmentId)`, `useDeleteTunnel(environmentId)`, `useRevealTunnelToken(environmentId)`, `useRefreshTunnelStatus(environmentId)`; `useTunnelHostnamesQuery(environmentId, tunnelId)`, `useAddTunnelHostname(environmentId, tunnelId)`, `useUpdateTunnelHostname(environmentId, tunnelId)`, `useRemoveTunnelHostname(environmentId, tunnelId)`.

- [ ] **Step 1: Write `use-tunnels.ts`**

Create `frontend/src/modules/cloudflare-tunnels/hooks/use-tunnels.ts`:

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTunnel,
  deleteTunnel,
  fetchTunnels,
  refreshTunnelStatus,
  revealTunnelToken,
} from "../api/fetchers";
import { cloudflareTunnelsKeys } from "../api/query-keys";

export function useTunnelsQuery(environmentId: string) {
  return useQuery({
    queryKey: cloudflareTunnelsKeys.list(environmentId),
    queryFn: () => fetchTunnels(environmentId),
  });
}

export function useCreateTunnel(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createTunnel(environmentId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
  });
}

export function useDeleteTunnel(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tunnelId: string) => deleteTunnel(environmentId, tunnelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
  });
}

export function useRevealTunnelToken(environmentId: string) {
  return useMutation({
    mutationFn: (tunnelId: string) => revealTunnelToken(environmentId, tunnelId),
  });
}

export function useRefreshTunnelStatus(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tunnelId: string) => refreshTunnelStatus(environmentId, tunnelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.list(environmentId) });
    },
  });
}
```

- [ ] **Step 2: Write `use-tunnel-hostnames.ts`**

Create `frontend/src/modules/cloudflare-tunnels/hooks/use-tunnel-hostnames.ts`:

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addTunnelHostname,
  fetchTunnelHostnames,
  removeTunnelHostname,
  updateTunnelHostname,
} from "../api/fetchers";
import { cloudflareTunnelsKeys } from "../api/query-keys";

export function useTunnelHostnamesQuery(environmentId: string, tunnelId: string, enabled: boolean) {
  return useQuery({
    queryKey: cloudflareTunnelsKeys.hostnames(environmentId, tunnelId),
    queryFn: () => fetchTunnelHostnames(environmentId, tunnelId),
    enabled,
  });
}

export function useAddTunnelHostname(environmentId: string, tunnelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { hostname: string; service: string }) =>
      addTunnelHostname(environmentId, tunnelId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.hostnames(environmentId, tunnelId) });
    },
  });
}

export function useUpdateTunnelHostname(environmentId: string, tunnelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ hostnameId, service }: { hostnameId: string; service: string }) =>
      updateTunnelHostname(environmentId, tunnelId, hostnameId, service),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.hostnames(environmentId, tunnelId) });
    },
  });
}

export function useRemoveTunnelHostname(environmentId: string, tunnelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (hostnameId: string) => removeTunnelHostname(environmentId, tunnelId, hostnameId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareTunnelsKeys.hostnames(environmentId, tunnelId) });
    },
  });
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/modules/cloudflare-tunnels/hooks/use-tunnels.ts src/modules/cloudflare-tunnels/hooks/use-tunnel-hostnames.ts
git commit -m "feat(cloudflare-tunnels): add query and mutation hooks"
```

---

## Task 17: Frontend — `CloudflareTunnelsPageContent` (mandatory `ui-ux-pro-max` invocation)

**Files:**
- Create: `frontend/src/modules/cloudflare-tunnels/ui/cloudflare-tunnels-page-content.tsx`
- Create: `frontend/src/modules/cloudflare-tunnels/ui/tunnel-status-badge.tsx`

**Interfaces:**
- Consumes: `useTunnelsQuery`, `useDeleteTunnel`, `useRefreshTunnelStatus` (Task 16), `useEnvironmentQuery` (existing, `@/entities/environment`), `CloudflareTunnel`/`TunnelStatus` (Task 15).
- Produces: `CloudflareTunnelsPageContent({ environmentId }: { environmentId: string })`, `TunnelStatusBadge({ status }: { status: TunnelStatus })`.

Per AGENTS.md's mandatory rule, this task touches layout/color/typography — invoke `ui-ux-pro-max` **before writing the markup**, not after.

- [ ] **Step 1: Query `ui-ux-pro-max` for status-badge and destructive-action guidance**

```bash
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "status badge icon color meaning" --domain ux
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "destructive confirm dialog" --domain ux
```

Apply the result while writing the component below: status must never be conveyed by color alone (icon + text label on every badge, matching the existing `DnsRecordFormDialog`'s `managedBy` badge precedent in `cloudflare-dns-page-content.tsx:89-92`), every icon-only button needs an `aria-label` and a `focus-visible:ring-2` (both already established conventions in `cloudflare-dns-page-content.tsx`), and the delete action reuses the existing hand-rolled `ConfirmDialog` atom with `variant="destructive"`.

- [ ] **Step 2: Write the status badge**

Create `frontend/src/modules/cloudflare-tunnels/ui/tunnel-status-badge.tsx`:

```tsx
import { CheckCircle2, AlertTriangle, XCircle, HelpCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import type { TunnelStatus } from "../model/schema";

const STATUS_STYLES: Record<TunnelStatus, { icon: typeof CheckCircle2; className: string }> = {
  healthy: {
    icon: CheckCircle2,
    className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300",
  },
  degraded: {
    icon: AlertTriangle,
    className: "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300",
  },
  down: {
    icon: XCircle,
    className: "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300",
  },
  unknown: {
    icon: HelpCircle,
    className: "bg-muted text-muted-foreground",
  },
};

export function TunnelStatusBadge({ status }: { status: TunnelStatus }) {
  const t = useTranslations("cloudflareTunnels");
  const { icon: Icon, className } = STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${className}`}
    >
      <Icon className="size-3" aria-hidden="true" />
      {t(`status.${status}`)}
    </span>
  );
}
```

- [ ] **Step 3: Write the page content**

Create `frontend/src/modules/cloudflare-tunnels/ui/cloudflare-tunnels-page-content.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Waypoints, Plus, Trash2, RefreshCw, KeyRound } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useEnvironmentQuery } from "@/entities/environment";
import { useTunnelsQuery, useDeleteTunnel, useRefreshTunnelStatus, useRevealTunnelToken } from "../hooks/use-tunnels";
import type { CloudflareTunnel } from "../model/schema";
import { TunnelStatusBadge } from "./tunnel-status-badge";
import { CreateTunnelDialog } from "./create-tunnel-dialog";
import { TunnelHostnamesPanel } from "./tunnel-hostnames-panel";

export function CloudflareTunnelsPageContent({ environmentId }: { environmentId: string }) {
  const t = useTranslations("cloudflareTunnels");
  const { data: environment } = useEnvironmentQuery(environmentId);
  const { data: tunnels = [] } = useTunnelsQuery(environmentId);
  const deleteTunnel = useDeleteTunnel(environmentId);
  const refreshStatus = useRefreshTunnelStatus(environmentId);
  const revealToken = useRevealTunnelToken(environmentId);

  const [createOpen, setCreateOpen] = useState(false);
  const [selectedTunnelId, setSelectedTunnelId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CloudflareTunnel | null>(null);
  const [revealedToken, setRevealedToken] = useState<{ tunnelId: string; token: string } | null>(null);

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{environment.name}</h1>
        <p className="text-sm text-muted-foreground">{t(`environmentTypes.${environment.type}`)}</p>
      </div>

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
            <Waypoints className="size-4" aria-hidden="true" /> {t("title")}
          </h2>
          <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-1.5 size-3.5" aria-hidden="true" /> {t("addTunnel")}
            </Button>
          </Can>
        </div>

        {tunnels.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <div className="flex flex-col divide-y">
            {tunnels.map((tunnel) => (
              <button
                key={tunnel.id}
                type="button"
                onClick={() => setSelectedTunnelId(tunnel.id)}
                className={`flex items-center justify-between py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                  selectedTunnelId === tunnel.id ? "bg-muted/40" : ""
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium text-foreground">{tunnel.name}</span>
                  <TunnelStatusBadge status={tunnel.status} />
                </div>
                <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                  <div className="flex items-center gap-3">
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={t("refreshStatus")}
                      onClick={(e) => {
                        e.stopPropagation();
                        refreshStatus.mutate(tunnel.id);
                      }}
                      className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <RefreshCw className="size-3.5" aria-hidden="true" />
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={t("revealToken")}
                      onClick={async (e) => {
                        e.stopPropagation();
                        const token = await revealToken.mutateAsync(tunnel.id);
                        setRevealedToken({ tunnelId: tunnel.id, token });
                      }}
                      className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <KeyRound className="size-3.5" aria-hidden="true" />
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={t("deleteConfirm.action")}
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTarget(tunnel);
                      }}
                      className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </span>
                  </div>
                </Can>
              </button>
            ))}
          </div>
        )}
      </section>

      {revealedToken && (
        <section className="flex flex-col gap-2 rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
          <p className="text-xs font-semibold uppercase text-amber-700 dark:text-amber-300">
            {t("tokenRevealed.title")}
          </p>
          <code className="break-all rounded bg-background px-2 py-1.5 font-mono text-xs">
            {revealedToken.token}
          </code>
          <p className="text-xs text-muted-foreground">{t("tokenRevealed.hint")}</p>
        </section>
      )}

      {selectedTunnelId && (
        <TunnelHostnamesPanel environmentId={environmentId} tunnelId={selectedTunnelId} />
      )}

      {createOpen && <CreateTunnelDialog environmentId={environmentId} onClose={() => setCreateOpen(false)} />}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteTunnel.mutate(deleteTarget.id, {
              onSuccess: () => {
                setDeleteTarget(null);
                if (selectedTunnelId === deleteTarget.id) setSelectedTunnelId(null);
              },
            });
          }
        }}
        title={t("deleteConfirm.title")}
        description={t("deleteConfirm.description", { name: deleteTarget?.name ?? "" })}
        variant="destructive"
        isLoading={deleteTunnel.isPending}
      />
    </div>
  );
}
```

- [ ] **Step 4: Typecheck (expect failures for the two not-yet-written imports — resolved by Task 18)**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors only for missing `./create-tunnel-dialog` and `./tunnel-hostnames-panel` modules — confirms everything else in this file typechecks. Do not commit yet; Task 18 completes this file's dependencies.

---

## Task 18: Frontend — create-tunnel dialog + hostnames panel (mandatory `ui-ux-pro-max` invocation)

**Files:**
- Create: `frontend/src/modules/cloudflare-tunnels/ui/create-tunnel-dialog.tsx`
- Create: `frontend/src/modules/cloudflare-tunnels/ui/tunnel-hostnames-panel.tsx`
- Create: `frontend/src/modules/cloudflare-tunnels/ui/hostname-form-dialog.tsx`
- Create: `frontend/src/modules/cloudflare-tunnels/index.ts`

**Interfaces:**
- Consumes: `useCreateTunnel` (Task 16), `useTunnelHostnamesQuery`/`useAddTunnelHostname`/`useUpdateTunnelHostname`/`useRemoveTunnelHostname` (Task 16), `TunnelPublicHostname` (Task 15).
- Produces: `CreateTunnelDialog({ environmentId, onClose })`, `TunnelHostnamesPanel({ environmentId, tunnelId })`, `HostnameFormDialog({ environmentId, tunnelId, hostname, onClose })`.

- [ ] **Step 1: Query `ui-ux-pro-max` for form-dialog and one-time-secret guidance**

```bash
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "modal dialog focus trap keyboard" --domain ux
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "inline validation error message" --domain ux
```

Apply the result: the hand-rolled dialogs below reuse the exact `shared/ui/dialog`-less pattern already established by `DnsRecordFormDialog`/`EnvironmentFormDialog` (no shadcn/Radix `Dialog` primitive in this repo — confirmed by the Phase 3 `ui-ux-pro-max` invocation's own finding, still true here), a labeled `<Input>`/`<Label>` pair per field (never placeholder-only labels), and the one-time connector token surfaced with a monospace `<code>` block plus a copy-to-clipboard affordance rather than a plain paragraph, mirroring the `revealedToken` treatment already written in Task 17.

- [ ] **Step 2: Write `create-tunnel-dialog.tsx`**

Create `frontend/src/modules/cloudflare-tunnels/ui/create-tunnel-dialog.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useCreateTunnel } from "../hooks/use-tunnels";

export function CreateTunnelDialog({ environmentId, onClose }: { environmentId: string; onClose: () => void }) {
  const t = useTranslations("cloudflareTunnels");
  const createTunnel = useCreateTunnel(environmentId);
  const [name, setName] = useState("");
  const [createdToken, setCreatedToken] = useState<string | null>(null);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-tunnel-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="w-full max-w-md rounded-xl border bg-card p-6 shadow-lg">
        <h2 id="create-tunnel-title" className="mb-4 text-base font-bold text-foreground">
          {t("createDialog.title")}
        </h2>

        {createdToken ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm font-semibold text-amber-700 dark:text-amber-300">
              {t("tokenRevealed.title")}
            </p>
            <code className="break-all rounded bg-muted px-2 py-1.5 font-mono text-xs">{createdToken}</code>
            <p className="text-xs text-muted-foreground">{t("tokenRevealed.hint")}</p>
            <div className="flex justify-end pt-2">
              <Button onClick={onClose}>{t("createDialog.done")}</Button>
            </div>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createTunnel.mutate(name, { onSuccess: (result) => setCreatedToken(result.token) });
            }}
            className="flex flex-col gap-4"
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tunnel-name">{t("createDialog.nameLabel")}</Label>
              <Input
                id="tunnel-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>
                {t("createDialog.cancel")}
              </Button>
              <Button type="submit" disabled={createTunnel.isPending || name.trim().length === 0}>
                {createTunnel.isPending ? t("createDialog.creating") : t("createDialog.create")}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write `tunnel-hostnames-panel.tsx`**

Create `frontend/src/modules/cloudflare-tunnels/ui/tunnel-hostnames-panel.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Globe, Plus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useTunnelHostnamesQuery, useRemoveTunnelHostname } from "../hooks/use-tunnel-hostnames";
import type { TunnelPublicHostname } from "../model/schema";
import { HostnameFormDialog } from "./hostname-form-dialog";

export function TunnelHostnamesPanel({ environmentId, tunnelId }: { environmentId: string; tunnelId: string }) {
  const t = useTranslations("cloudflareTunnels");
  const { data: hostnames = [] } = useTunnelHostnamesQuery(environmentId, tunnelId, true);
  const removeHostname = useRemoveTunnelHostname(environmentId, tunnelId);

  const [formTarget, setFormTarget] = useState<TunnelPublicHostname | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TunnelPublicHostname | null>(null);

  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Globe className="size-4" aria-hidden="true" /> {t("hostnames.title")}
        </h2>
        <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
          <Button size="sm" onClick={() => setFormTarget("create")}>
            <Plus className="mr-1.5 size-3.5" aria-hidden="true" /> {t("hostnames.add")}
          </Button>
        </Can>
      </div>

      {hostnames.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("hostnames.empty")}</p>
      ) : (
        <div className="flex flex-col divide-y">
          {hostnames.map((hostname) => (
            <div key={hostname.id} className="flex items-center justify-between py-2 text-sm">
              <div className="flex flex-col">
                <span className="font-medium text-foreground">{hostname.hostname}</span>
                <span className="text-xs text-muted-foreground">{hostname.service}</span>
              </div>
              <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setFormTarget(hostname)}
                    aria-label={t("hostnames.edit")}
                    className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <Pencil className="size-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(hostname)}
                    aria-label={t("hostnames.remove")}
                    className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <Trash2 className="size-3.5" aria-hidden="true" />
                  </button>
                </div>
              </Can>
            </div>
          ))}
        </div>
      )}

      {formTarget !== null && (
        <HostnameFormDialog
          environmentId={environmentId}
          tunnelId={tunnelId}
          hostname={formTarget === "create" ? null : formTarget}
          onClose={() => setFormTarget(null)}
        />
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            removeHostname.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
        title={t("hostnames.deleteConfirm.title")}
        description={t("hostnames.deleteConfirm.description", { hostname: deleteTarget?.hostname ?? "" })}
        variant="destructive"
        isLoading={removeHostname.isPending}
      />
    </section>
  );
}
```

- [ ] **Step 4: Write `hostname-form-dialog.tsx`**

Create `frontend/src/modules/cloudflare-tunnels/ui/hostname-form-dialog.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useAddTunnelHostname, useUpdateTunnelHostname } from "../hooks/use-tunnel-hostnames";
import type { TunnelPublicHostname } from "../model/schema";

export function HostnameFormDialog({
  environmentId,
  tunnelId,
  hostname,
  onClose,
}: {
  environmentId: string;
  tunnelId: string;
  hostname: TunnelPublicHostname | null;
  onClose: () => void;
}) {
  const t = useTranslations("cloudflareTunnels");
  const isEditing = hostname !== null;
  const addHostname = useAddTunnelHostname(environmentId, tunnelId);
  const updateHostname = useUpdateTunnelHostname(environmentId, tunnelId);
  const [hostnameValue, setHostnameValue] = useState(hostname?.hostname ?? "");
  const [service, setService] = useState(hostname?.service ?? "");

  const isSaving = addHostname.isPending || updateHostname.isPending;
  const conflictError =
    addHostname.error instanceof Error && addHostname.error.message.includes("locked");

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="hostname-form-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="w-full max-w-md rounded-xl border bg-card p-6 shadow-lg">
        <h2 id="hostname-form-title" className="mb-4 text-base font-bold text-foreground">
          {isEditing ? t("hostnames.editTitle") : t("hostnames.addTitle")}
        </h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (isEditing) {
              updateHostname.mutate(
                { hostnameId: hostname.id, service },
                { onSuccess: onClose },
              );
            } else {
              addHostname.mutate({ hostname: hostnameValue, service }, { onSuccess: onClose });
            }
          }}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hostname-value">{t("hostnames.hostnameLabel")}</Label>
            <Input
              id="hostname-value"
              value={hostnameValue}
              onChange={(e) => setHostnameValue(e.target.value)}
              disabled={isEditing}
              required
              autoFocus={!isEditing}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hostname-service">{t("hostnames.serviceLabel")}</Label>
            <Input
              id="hostname-service"
              value={service}
              onChange={(e) => setService(e.target.value)}
              placeholder="http://localhost:8080"
              required
              autoFocus={isEditing}
            />
          </div>
          {conflictError && (
            <p className="text-xs text-destructive">{t("hostnames.lockedError")}</p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("hostnames.cancel")}
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? t("hostnames.saving") : t("hostnames.save")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Write the module's `index.ts`**

Create `frontend/src/modules/cloudflare-tunnels/index.ts`:

```typescript
export { CloudflareTunnelsPageContent } from "./ui/cloudflare-tunnels-page-content";
```

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors across the whole `modules/cloudflare-tunnels/` tree.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add src/modules/cloudflare-tunnels/
git commit -m "feat(cloudflare-tunnels): add tunnel and hostname UI (ui-ux-pro-max applied)"
```

---

## Task 19: Route, nav entry, i18n wiring

**Files:**
- Create: `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/tunnels/page.tsx`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/tunnels/loading.tsx`
- Modify: `frontend/src/modules/projects/ui/project-detail-view.tsx`
- Create: `frontend/locales/en/modules/cloudflare-tunnels.json`
- Create: `frontend/locales/vi/modules/cloudflare-tunnels.json`
- Modify: `frontend/src/shared/lib/i18n/request.ts`
- Modify: `frontend/locales/en/modules/projects.json` and `frontend/locales/vi/modules/projects.json`

**Interfaces:**
- Produces: the `admin/environments/[environmentId]/tunnels` route; a new "Manage Tunnels" icon-link on each environment chip in `ProjectDetailView`, alongside the existing DNS link; the `cloudflareTunnels` i18n namespace registered in `request.ts`.

- [ ] **Step 1: Write the route**

Create `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/tunnels/page.tsx`, mirroring the DNS route in `.../dns/page.tsx` exactly (same SSR-prefetch-only-the-environment, same permission guard):

```tsx
import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchEnvironmentById, environmentsKeys } from "@/entities/environment";
import { CloudflareTunnelsPageContent } from "@/modules/cloudflare-tunnels";

export default async function AdminEnvironmentTunnelsPage({
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
        <CloudflareTunnelsPageContent environmentId={environmentId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
```

Create `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/tunnels/loading.tsx` — copy the existing `.../dns/loading.tsx` file verbatim (read it first; it's a generic skeleton with no DNS-specific content, so it applies unchanged).

- [ ] **Step 2: Add the nav affordance to `project-detail-view.tsx`**

In `frontend/src/modules/projects/ui/project-detail-view.tsx`, add `Waypoints` to the existing `lucide-react` import line (`import { Plus, Pencil, Trash2, Server, Link2, Globe } from "lucide-react";` → add `Waypoints`), then add a second icon-link immediately after the existing DNS `<Link>` block (inside the same `<Can I={ACTIONS.VIEW} a={RESOURCES.CLOUDFLARE_ACCOUNT}>` guard's sibling, as its own `<Can>`):

```tsx
              <Can I={ACTIONS.VIEW} a={RESOURCES.CLOUDFLARE_ACCOUNT}>
                <Link
                  href={`/admin/environments/${env.id}/tunnels`}
                  className="text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  aria-label={t("actions.manageTunnels")}
                >
                  <Waypoints className="size-3.5" />
                </Link>
              </Can>
```

Place this directly after the existing DNS `<Link>`'s closing `</Can>` (before the `Pencil`/edit `<Can>` block), so the chip's icon order reads: DNS → Tunnels → Edit → Delete.

- [ ] **Step 3: Add the `manageTunnels` translation key**

In `frontend/locales/en/modules/projects.json`, add `"manageTunnels": "Manage Tunnels"` next to the existing `"manageDns"` key inside `actions`. In `frontend/locales/vi/modules/projects.json`, add the Vietnamese equivalent next to its own `manageDns` entry (read both files first to match the exact existing key style/casing before adding).

- [ ] **Step 4: Write the `cloudflareTunnels` locale files**

Create `frontend/locales/en/modules/cloudflare-tunnels.json`:

```json
{
  "title": "Tunnels",
  "addTunnel": "Add Tunnel",
  "empty": "No tunnels yet.",
  "refreshStatus": "Refresh status",
  "revealToken": "Reveal connector token",
  "status": {
    "healthy": "Healthy",
    "degraded": "Degraded",
    "down": "Down",
    "unknown": "Unknown"
  },
  "tokenRevealed": {
    "title": "Connector token",
    "hint": "Copy this now — it will not be shown here again. Use it with `cloudflared tunnel run --token <token>`."
  },
  "deleteConfirm": {
    "action": "Delete tunnel",
    "title": "Delete this tunnel?",
    "description": "This will delete '{name}' and every hostname published through it on Cloudflare."
  },
  "createDialog": {
    "title": "Create Tunnel",
    "nameLabel": "Name",
    "cancel": "Cancel",
    "create": "Create",
    "creating": "Creating...",
    "done": "Done"
  },
  "hostnames": {
    "title": "Public Hostnames",
    "add": "Add Hostname",
    "empty": "No hostnames published yet.",
    "edit": "Edit hostname",
    "remove": "Remove hostname",
    "addTitle": "Add Hostname",
    "editTitle": "Edit Hostname",
    "hostnameLabel": "Hostname",
    "serviceLabel": "Service",
    "cancel": "Cancel",
    "save": "Save",
    "saving": "Saving...",
    "lockedError": "Someone else is editing this tunnel right now — try again in a moment.",
    "deleteConfirm": {
      "title": "Remove this hostname?",
      "description": "'{hostname}' will stop being routed through this tunnel."
    }
  },
  "environmentTypes": {}
}
```

For the `environmentTypes` object, copy the exact contents from `frontend/locales/en/modules/cloudflare-dns.json`'s own `environmentTypes` key verbatim (read that file first — do not guess the values). Repeat the same structure for `frontend/locales/vi/modules/cloudflare-tunnels.json`, translating every string to Vietnamese and copying `environmentTypes` from `frontend/locales/vi/modules/cloudflare-dns.json`.

- [ ] **Step 5: Register the namespace in `request.ts`**

In `frontend/src/shared/lib/i18n/request.ts`, add `cloudflareTunnels` to the `Promise.all` import array and the returned `messages` object, following the exact pattern the file already uses for `cloudflareDns`:

```typescript
  const [common, auth, users, roles, projects, auditLog, cloudflareAccounts, cloudflareDns, cloudflareTunnels] =
    await Promise.all([
      import(`../../../../locales/${locale}/common.json`),
      import(`../../../../locales/${locale}/modules/auth.json`),
      import(`../../../../locales/${locale}/modules/users.json`),
      import(`../../../../locales/${locale}/modules/roles.json`),
      import(`../../../../locales/${locale}/modules/projects.json`),
      import(`../../../../locales/${locale}/modules/audit-log.json`),
      import(`../../../../locales/${locale}/modules/cloudflare-accounts.json`),
      import(`../../../../locales/${locale}/modules/cloudflare-dns.json`),
      import(`../../../../locales/${locale}/modules/cloudflare-tunnels.json`),
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
      cloudflareTunnels: cloudflareTunnels.default,
    },
  };
```

- [ ] **Step 6: Typecheck, lint, build**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.

Run: `cd frontend && npm run build`
Expected: build succeeds; the new `admin/environments/[environmentId]/tunnels` route appears in the build's route manifest output.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add src/app/'[locale]'/'(dashboard)'/admin/environments/'[environmentId]'/tunnels/ src/modules/projects/ui/project-detail-view.tsx locales/en/modules/cloudflare-tunnels.json locales/vi/modules/cloudflare-tunnels.json locales/en/modules/projects.json locales/vi/modules/projects.json src/shared/lib/i18n/request.ts
git commit -m "feat(cloudflare-tunnels): add route, nav affordance, i18n wiring"
```

---

## Task 20: Whole-phase verification and finish

**Files:** none (verification only).

- [ ] **Step 1: Full backend verification**

```bash
cd backend
ruff check
ruff format --check
python scripts/check_module_boundaries.py --strict
lint-imports
uv run pytest -q
```

Expected: all green, including every new test from Tasks 1-14 and zero regressions in pre-existing tests.

- [ ] **Step 2: Full frontend verification**

```bash
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

Expected: all green; `admin/environments/[environmentId]/tunnels` appears in the build output's route list alongside the existing `.../dns` route.

- [ ] **Step 3: GitNexus re-index and diff review**

```bash
node .gitnexus/run.cjs analyze
git diff develop..feature/cloudflare-tunnels --stat
```

Confirm the touched-files list matches this plan's Architecture Impact section: `backend/app/integrations/cloudflare/client.py`, `backend/app/modules/cloudflare/*` (constants/models/schemas/exceptions/repository/uow/dependencies/router), 8 new `backend/app/modules/cloudflare/services/*.py` files, 1 new alembic migration, `frontend/src/modules/cloudflare-tunnels/*` (new), `frontend/src/modules/projects/ui/project-detail-view.tsx`, `frontend/src/shared/constants/api.ts`, `frontend/src/shared/lib/i18n/request.ts`, 4 locale JSON files, and the new route files. No `.importlinter` change is expected (per the plan's own note — both packages' contracts already cover this pairing from Phase 3/4). Any file outside this list is unexpected blast radius — stop and investigate before proceeding.

- [ ] **Step 4: Manual smoke test against `itsm_test`**

Run the Phase 5 demo script from the master plan verbatim, against the `itsm_test` sibling database (never `business-chatbot-postgres`'s live `itsm` database):
1. Bind an environment to a Cloudflare account/zone (reuse Phase 4's binding flow) if not already bound.
2. Create a tunnel → confirm the one-time connector token is shown exactly once in the create dialog.
3. Add 2 hostnames to the tunnel → confirm both appear in the hostnames table.
4. Open two browser tabs on the same tunnel's hostname form and submit two near-simultaneous adds → confirm the second request surfaces a 409/locked error rather than silently overwriting the first (Decision #1).
5. Click "Refresh status" → confirm the status badge updates (will show DOWN/UNKNOWN against a fake/sandboxed Cloudflare tunnel with no real `cloudflared` connector running — this is expected, not a bug).
6. Delete the tunnel → confirm both the tunnel and its hostnames disappear, with no orphaned rows.

- [ ] **Step 5: Invoke `finishing-a-development-branch`**

Once Steps 1-4 are all green, use the `finishing-a-development-branch` skill: verify tests (already done in Steps 1-2), detect environment (normal repo, no worktree — matches every prior phase this session), present the standard 3-option menu (merge locally / push+PR / keep as-is), and execute whichever option the user picks. Base branch is `develop`, matching every prior phase.

---
