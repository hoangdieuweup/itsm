# DevOps Panel Phase 6 — Loki Log Viewer + Cloudflare Audit Logs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user configure Loki connection details per environment and run LogQL `query_range` queries from within the app, plus view that environment's Cloudflare Audit Log entries (config-change history, not raw traffic — Logpull is Enterprise-only and was dropped) side by side in a two-tab log viewer.

**Architecture:** New `app/integrations/loki/` client leaf (stateless, mirrors `app/integrations/cloudflare/client.py`). New `app/modules/observability/` module owning `loki_configs` (1:1 per environment, no 2-layer ACL — gated by the existing `environment:read`/`environment:update` RBAC permissions, zero new catalog rows). One new method (`get_account_audit_logs`) added to the *existing* `CloudflareClient`, and one new route added to the *existing* `app/modules/cloudflare/router.py` — the Cloudflare Audit Log tab stays inside `cloudflare/` to reuse its 2-layer ACL rather than growing a new cross-module facade. Frontend `modules/log-viewer/` mirrors `modules/cloudflare-dns/`'s file-by-file shape exactly.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, httpx, pydantic-settings, cryptography (Fernet), Next.js App Router, TanStack Query, Zod, next-intl.

**Spec:** The "Phase 6 — Detailed Plan: `loki_configs` + query-time log viewer" section of `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md` (10 numbered Decisions — this plan does not implement the naive version of any of them). Also `docs/tasks/grafana-loki-integration.md` (Loki HTTP API reference) and `docs/tasks/cloudflare-api-reference.md` §6 (Audit Logs).

## Global Constraints

- Logpull is dropped from this phase entirely (Enterprise-plan-only) — the "Cloudflare traffic" tab is a Cloudflare **Audit Logs** tab instead (Decision preamble).
- Cloudflare Audit Logs endpoint lives inside the existing `app/modules/cloudflare/` module, reusing its 2-layer ACL — no new facade method on `cloudflare/public.py` (Decision #1).
- `loki_configs` gating reuses `RbacResources.ENVIRONMENT` / `RbacActions.READ|UPDATE` — **zero new RBAC catalog rows** (Decision #2).
- `.importlinter`: new `observability-facade` stanza; `app.modules.observability` added to `rbac-facade`, `users-facade`, `projects-facade`, `audit-facade` source_modules (Decision #3).
- `loki_configs.credential` Fernet-encrypted with a new `OBSERVABILITY__FERNET_KEY`, mirroring `cloudflare/config.py`'s exact shape (Decision #4). BASIC auth stores plaintext `"username:password"` in the single `credential` column; BEARER stores the raw token; NONE sends no header.
- `LokiClient.query_range` takes `endpoint_url` as a per-call argument (not a settings base URL) since every environment can point at a different Loki cluster (Decision #5). Flattens multi-stream results into a single chronologically-sorted `list[LokiLogEntry]`.
- Loki error mapping is 3-way: `LokiApiUnavailable` (transport/5xx), `InvalidLokiCredential` (401/403), `LokiQueryRejected` (other 4xx, carries Loki's own error message) (Decision #6).
- `CloudflareClient.get_account_audit_logs` reuses the existing `_write` helper, same as the Tunnel GET methods already do — failures surface as the existing `CloudflareDnsOperationRejected`, not a new exception (Decision #7).
- `CloudflareAuditLogEntry` is a deliberately narrow, purpose-built schema (`id`, `when`, `actor_email`, `actor_ip`, `action_type`, `resource_type`, `resource_product`, `new_value`) — not a pass-through of Cloudflare's full entry shape (Decision #8).
- No caching for `loki_configs`/audit-log reads (Decision #9). Frontend stays module-local, no new `entities/` folder (Decision #10).
- Router thinness (rule #10) and class-scoped constants (rule #16) apply throughout, exactly as every prior phase.
- Alembic `down_revision = "f3a8c1d9e4b7"` (confirmed current head).
- Any UI code in Task 14 MUST invoke the `ui-ux-pro-max` plugin per AGENTS.md — query its style/palette/a11y database while writing the two-tab layout, time-range picker, and results tables.

---

## Task 1: `app/integrations/loki/` — config, constants, exceptions, schemas

**Files:**
- Create: `backend/app/integrations/loki/__init__.py` (empty)
- Create: `backend/app/integrations/loki/config.py`
- Create: `backend/app/integrations/loki/constants.py`
- Create: `backend/app/integrations/loki/exceptions.py`
- Create: `backend/app/integrations/loki/schemas.py`
- Test: `backend/tests/integrations/loki/test_schemas.py`

**Interfaces:**
- Produces: `loki_settings: LokiIntegrationConfig` (`.HTTP_TIMEOUT_SECONDS: float`), `LokiErrorCode(StrEnum)`, `LokiApiUnavailable`, `InvalidLokiCredential`, `LokiQueryRejected`, `LokiLogEntry(timestamp: str, line: str, labels: dict[str, str])`, `LokiQueryResult(entries: list[LokiLogEntry])`.

- [ ] **Step 1: Write the failing test for `LokiQueryResult` sorting behavior**

```python
# backend/tests/integrations/loki/test_schemas.py
from app.integrations.loki.schemas import LokiLogEntry, LokiQueryResult


def test_loki_query_result_holds_entries_as_given():
    entries = [
        LokiLogEntry(timestamp="1700000002000000000", line="second", labels={"job": "api"}),
        LokiLogEntry(timestamp="1700000001000000000", line="first", labels={"job": "api"}),
    ]
    result = LokiQueryResult(entries=entries)
    assert [e.line for e in result.entries] == ["second", "first"]
    assert result.entries[0].labels == {"job": "api"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integrations/loki/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.integrations.loki'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/integrations/loki/config.py
"""Settings owned by the loki integration — transport only. Unlike Cloudflare's
single shared API_BASE_URL, every environment can point at a different Loki
cluster (loki_configs.endpoint_url is a per-row column), so there is no
base-URL setting here — callers pass endpoint_url per call."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class LokiIntegrationConfig(BaseSettings):
    """Environment driven settings for the Loki HTTP client."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LOKI__", extra="ignore")

    HTTP_TIMEOUT_SECONDS: float = 10.0


loki_settings = LokiIntegrationConfig()
```

```python
# backend/app/integrations/loki/constants.py
from enum import StrEnum


class LokiErrorCode(StrEnum):
    UNAVAILABLE = "loki_unavailable"
    INVALID_CREDENTIAL = "loki_invalid_credential"
    QUERY_REJECTED = "loki_query_rejected"
```

```python
# backend/app/integrations/loki/exceptions.py
"""Errors owned by the loki integration — transport/protocol failures only.
Domain-level errors (LokiConfigNotFound, etc.) live in
app.modules.observability.exceptions instead."""

from app.core.exceptions import IntegrationError, ValidationFailedError
from app.integrations.loki.constants import LokiErrorCode


class LokiApiUnavailable(IntegrationError):
    """Raised when the Loki API cannot be reached or returns a server error."""

    code = LokiErrorCode.UNAVAILABLE
    message = "Loki API unavailable"


class InvalidLokiCredential(ValidationFailedError):
    """Raised when Loki rejects the provided credential (401/403)."""

    code = LokiErrorCode.INVALID_CREDENTIAL
    message = "Loki rejected the provided credential"


class LokiQueryRejected(ValidationFailedError):
    """Raised when Loki rejects the query itself (malformed LogQL, etc.) —
    distinct from InvalidLokiCredential, which is specifically about auth.
    Carries Loki's own error message so a bad-syntax query reaches the user
    as a specific, actionable string."""

    code = LokiErrorCode.QUERY_REJECTED
    message = "Loki rejected this query"
```

```python
# backend/app/integrations/loki/schemas.py
from pydantic import BaseModel


class LokiLogEntry(BaseModel):
    timestamp: str
    line: str
    labels: dict[str, str]


class LokiQueryResult(BaseModel):
    entries: list[LokiLogEntry]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/integrations/loki/test_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/loki backend/tests/integrations/loki/test_schemas.py
git commit -m "feat(loki): add integration config, constants, exceptions, schemas"
```

---

## Task 2: `LokiClient.query_range`

**Files:**
- Create: `backend/app/integrations/loki/client.py`
- Test: `backend/tests/integrations/loki/test_client.py`

**Interfaces:**
- Consumes: `loki_settings` (Task 1), `LokiApiUnavailable`/`InvalidLokiCredential`/`LokiQueryRejected` (Task 1), `LokiLogEntry`/`LokiQueryResult` (Task 1).
- Produces: `LokiClient(transport: httpx.AsyncBaseTransport | None = None)` with `async def query_range(self, *, endpoint_url: str, query: str, start: datetime, end: datetime, tenant_id: str | None, auth_header: str | None, limit: int = 200) -> LokiQueryResult`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integrations/loki/test_client.py
from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.loki.client import LokiClient
from app.integrations.loki.exceptions import InvalidLokiCredential, LokiApiUnavailable, LokiQueryRejected

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 1, 1, tzinfo=UTC)


def _client(handler):
    return LokiClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_query_range_flattens_and_sorts_multi_stream_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/loki/api/v1/query_range"
        assert request.headers.get("Authorization") == "Bearer tok"
        assert request.headers.get("X-Scope-OrgID") == "tenant-a"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {"stream": {"job": "api"}, "values": [["1700000002000000000", "second"]]},
                        {"stream": {"job": "web"}, "values": [["1700000001000000000", "first"]]},
                    ],
                },
            },
        )

    result = await _client(handler).query_range(
        endpoint_url="http://loki:3100",
        query='{job="api"}',
        start=START,
        end=END,
        tenant_id="tenant-a",
        auth_header="Bearer tok",
    )
    assert [e.line for e in result.entries] == ["first", "second"]
    assert result.entries[0].labels == {"job": "web"}


@pytest.mark.asyncio
async def test_query_range_empty_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success", "data": {"resultType": "streams", "result": []}})

    result = await _client(handler).query_range(
        endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
    )
    assert result.entries == []


@pytest.mark.asyncio
async def test_query_range_401_raises_invalid_credential():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": "error", "error": "no orgId"})

    with pytest.raises(InvalidLokiCredential):
        await _client(handler).query_range(
            endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
        )


@pytest.mark.asyncio
async def test_query_range_400_raises_rejected_with_loki_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"status": "error", "error": "parse error: unexpected IDENTIFIER"})

    with pytest.raises(LokiQueryRejected, match="parse error: unexpected IDENTIFIER"):
        await _client(handler).query_range(
            endpoint_url="http://loki:3100", query="{bad", start=START, end=END, tenant_id=None, auth_header=None
        )


@pytest.mark.asyncio
async def test_query_range_500_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"status": "error", "error": "internal"})

    with pytest.raises(LokiApiUnavailable):
        await _client(handler).query_range(
            endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
        )


@pytest.mark.asyncio
async def test_query_range_transport_failure_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LokiApiUnavailable):
        await _client(handler).query_range(
            endpoint_url="http://loki:3100", query="{}", start=START, end=END, tenant_id=None, auth_header=None
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integrations/loki/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.integrations.loki.client'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/integrations/loki/client.py
"""Loki HTTP API client. HTTP only — no database, no business logic. Lives
here (not app/modules/observability/) mirroring the same integration/module
split app/integrations/cloudflare/ already established in this repo."""

from datetime import datetime

import httpx

from app.core.base.markers import integration
from app.integrations.loki.config import loki_settings
from app.integrations.loki.exceptions import InvalidLokiCredential, LokiApiUnavailable, LokiQueryRejected
from app.integrations.loki.schemas import LokiLogEntry, LokiQueryResult


class LokiClient:
    """Talks to a Loki HTTP API. One instance per request, built in
    dependencies.py. `transport` is injectable only for tests — production
    code always constructs LokiClient() with no arguments. Unlike
    CloudflareClient, endpoint_url is a per-call argument, not a settings
    base URL, since every environment can point at a different cluster."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @integration
    async def query_range(
        self,
        *,
        endpoint_url: str,
        query: str,
        start: datetime,
        end: datetime,
        tenant_id: str | None,
        auth_header: str | None,
        limit: int = 200,
    ) -> LokiQueryResult:
        """GET {endpoint_url}/loki/api/v1/query_range. start/end sent as Unix
        nanosecond timestamps (Loki's canonical format). auth_header is the
        fully-built header value ("Basic <b64>" / "Bearer <token>" / None) —
        built by the caller, keeping this client ignorant of auth_type as a
        concept. Flattens every stream's values into one chronologically
        sorted list — display-only data, unlike Cloudflare's tunnel-ingress
        writes, so flattening (not raw-JSON preservation) is correct here."""
        headers = {}
        if auth_header is not None:
            headers["Authorization"] = auth_header
        if tenant_id is not None:
            headers["X-Scope-OrgID"] = tenant_id

        params = {
            "query": query,
            "start": str(int(start.timestamp() * 1_000_000_000)),
            "end": str(int(end.timestamp() * 1_000_000_000)),
            "limit": limit,
        }

        try:
            async with httpx.AsyncClient(base_url=endpoint_url, transport=self._transport) as client:
                response = await client.get(
                    "/loki/api/v1/query_range",
                    params=params,
                    headers=headers,
                    timeout=loki_settings.HTTP_TIMEOUT_SECONDS,
                )
        except httpx.HTTPError as exc:
            raise LokiApiUnavailable() from exc

        if response.status_code in (401, 403):
            raise InvalidLokiCredential()
        if response.status_code >= 500:
            raise LokiApiUnavailable(status_code=response.status_code)
        body = response.json()
        if response.is_error:
            raise LokiQueryRejected(message=body.get("error", "Loki rejected this query"))

        entries = [
            LokiLogEntry(timestamp=ts, line=line, labels=stream.get("stream", {}))
            for stream in body.get("data", {}).get("result", [])
            for ts, line in stream.get("values", [])
        ]
        entries.sort(key=lambda e: e.timestamp)
        return LokiQueryResult(entries=entries)
```

Note: `LokiQueryRejected(message=...)` requires the exception base class to accept a `message` override — confirm during implementation that `ValidationFailedError` (in `app/core/exceptions.py`) supports a per-instance `message` kwarg the same way `CloudflareApiUnavailable(status_code=...)` does for `IntegrationError`; if the base class only supports a class-level `message` attribute, add an `__init__(self, message: str | None = None)` override to `LokiQueryRejected` that falls back to the class default when `message` is `None`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integrations/loki/test_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/loki/client.py backend/tests/integrations/loki/test_client.py
git commit -m "feat(loki): add LokiClient.query_range with stream flattening"
```

---

## Task 3: `CloudflareClient.get_account_audit_logs` + `CloudflareAuditLogEntry`

**Files:**
- Modify: `backend/app/integrations/cloudflare/client.py`
- Modify: `backend/app/integrations/cloudflare/schemas.py`
- Test: `backend/tests/integrations/cloudflare/test_client.py`

**Interfaces:**
- Produces: `CloudflareAuditLogEntry(id, when, actor_email, actor_ip, action_type, resource_type, resource_product, new_value)`, `CloudflareClient.get_account_audit_logs(*, cf_account_id: str, api_token: str, zone_name: str, since: datetime | None, before: datetime | None) -> list[CloudflareAuditLogEntry]`.

- [ ] **Step 1: Write the failing tests**

Read `backend/tests/integrations/cloudflare/test_client.py` first to copy its exact existing fixture/helper style (`_client(handler)` or equivalent) before adding these — do not diverge from the established test-file convention.

```python
# append to backend/tests/integrations/cloudflare/test_client.py

@pytest.mark.asyncio
async def test_get_account_audit_logs_filters_by_zone_and_maps_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/accounts/acc-1/audit_logs"
        assert request.url.params["zone.name"] == "example.com"
        assert request.url.params["since"] == "2026-01-01T00:00:00+00:00"
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "id": "log-1",
                        "when": "2026-01-01T00:05:00Z",
                        "actor": {"email": "a@b.com", "ip": "1.2.3.4"},
                        "action": {"type": "update"},
                        "resource": {"type": "dns_record", "product": "dns"},
                        "newValue": "1.2.3.4",
                    }
                ],
            },
        )

    entries = await _client(handler).get_account_audit_logs(
        cf_account_id="acc-1",
        api_token="tok",
        zone_name="example.com",
        since=datetime(2026, 1, 1, tzinfo=UTC),
        before=None,
    )
    assert len(entries) == 1
    assert entries[0].id == "log-1"
    assert entries[0].actor_email == "a@b.com"
    assert entries[0].action_type == "update"
    assert entries[0].resource_product == "dns"
    assert entries[0].new_value == "1.2.3.4"


@pytest.mark.asyncio
async def test_get_account_audit_logs_rejected_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"success": False, "errors": [{"message": "forbidden"}]})

    with pytest.raises(CloudflareDnsOperationRejected):
        await _client(handler).get_account_audit_logs(
            cf_account_id="acc-1", api_token="tok", zone_name="example.com", since=None, before=None
        )
```

(Adjust the exact `_client`/fixture name and `datetime`/`UTC`/`httpx`/`pytest` import lines to match whatever the existing top of `test_client.py` already uses — read it first, this is a mirror, not a rewrite.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integrations/cloudflare/test_client.py -k audit_logs -v`
Expected: FAIL with `AttributeError: 'CloudflareClient' object has no attribute 'get_account_audit_logs'`

- [ ] **Step 3: Write the implementation**

```python
# add to backend/app/integrations/cloudflare/schemas.py

from pydantic import BaseModel


class CloudflareAuditLogEntry(BaseModel):
    """A deliberately narrow, purpose-built read-model of one Cloudflare
    account audit log entry — not a pass-through of Cloudflare's full (large,
    evolving) entry shape. Extend with more fields only when a real consumer
    needs them (e.g. a future phase wanting resource.id for deep-linking)."""

    id: str
    when: str
    actor_email: str | None
    actor_ip: str | None
    action_type: str
    resource_type: str | None
    resource_product: str | None
    new_value: str | None
```

```python
# add to backend/app/integrations/cloudflare/client.py, near the other @integration methods

    @integration
    async def get_account_audit_logs(
        self,
        *,
        cf_account_id: str,
        api_token: str,
        zone_name: str,
        since: datetime | None,
        before: datetime | None,
    ) -> list[CloudflareAuditLogEntry]:
        """GET /accounts/{cf_account_id}/audit_logs?zone.name=<zone_name>.
        zone.name filters to just this environment's bound zone per the
        reference doc's own recommendation — never returns account-wide
        entries for other zones this environment doesn't own. Reuses _write
        (the de-facto generic "authenticated call + envelope check" helper —
        3 existing Tunnel GET methods already reuse it too) rather than a
        new helper; failures surface as CloudflareDnsOperationRejected,
        consistent with that existing precedent, not a scope-creeping rename."""
        params: dict[str, str] = {"zone.name": zone_name}
        if since is not None:
            params["since"] = since.isoformat()
        if before is not None:
            params["before"] = before.isoformat()
        query = "&".join(f"{k}={v}" for k, v in params.items())
        body = await self._write(f"/accounts/{cf_account_id}/audit_logs?{query}", "GET", api_token)
        return [
            CloudflareAuditLogEntry(
                id=entry["id"],
                when=entry["when"],
                actor_email=entry.get("actor", {}).get("email"),
                actor_ip=entry.get("actor", {}).get("ip"),
                action_type=entry.get("action", {}).get("type", ""),
                resource_type=entry.get("resource", {}).get("type"),
                resource_product=entry.get("resource", {}).get("product"),
                new_value=entry.get("newValue"),
            )
            for entry in body.get("result", [])
        ]
```

Add `from datetime import datetime` and `from app.integrations.cloudflare.schemas import CloudflareAuditLogEntry, ZoneOption` (extend the existing schemas import line) to `client.py`'s imports. Note `_write` builds the request via `client.request(method, path, ...)` where `path` is passed as-is — confirm during implementation whether `httpx`'s `AsyncClient.request` accepts a path with an inline query string this way (it does, since `path` is passed straight to `httpx`, which parses query strings embedded in the URL/path argument) or whether `_write`'s signature needs a `params: dict | None` kwarg added instead (cleaner, mirrors `list_zones`'s explicit `params=` usage) — prefer adding `params` support to `_write` if it doesn't already exist, rather than string-concatenating a query string, since every other GET in this client passes `params=` as a dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integrations/cloudflare/test_client.py -v`
Expected: PASS (all existing + 2 new tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/cloudflare/client.py backend/app/integrations/cloudflare/schemas.py backend/tests/integrations/cloudflare/test_client.py
git commit -m "feat(cloudflare): add get_account_audit_logs client method"
```

---

## Task 4: `app/modules/observability/` — config, constants, models, schemas, exceptions

**Files:**
- Create: `backend/app/modules/observability/__init__.py` (empty)
- Create: `backend/app/modules/observability/config.py`
- Create: `backend/app/modules/observability/constants.py`
- Create: `backend/app/modules/observability/models.py`
- Create: `backend/app/modules/observability/schemas.py`
- Create: `backend/app/modules/observability/exceptions.py`
- Test: `backend/tests/observability/test_models.py`

**Interfaces:**
- Consumes: `FernetCodec` (`app.core.crypto`), `Base` (SQLAlchemy declarative base — read `app/modules/cloudflare/models.py`'s import line for the exact source path before writing this).
- Produces: `LokiAuthType(StrEnum)`, `ObservabilityLimits`, `ErrorCode(StrEnum)`, `ObservabilityAuditActions(StrEnum)`, `LokiConfig` (model), `LokiConfigRead`/`Create`/`Update`, `LogQueryRequest`/`LogQueryResponse`, `LokiConfigNotFound`, `LokiConfigAlreadyExists`, `ObservabilityEnvironmentNotFound`.

- [ ] **Step 1: Write the failing test**

First read `backend/app/modules/cloudflare/models.py`'s imports (exact `Base`/`Mapped`/`mapped_column` source paths) and `backend/tests/cloudflare/test_repository.py` (or wherever an existing model gets its first smoke test) to copy the exact declarative-model test pattern used elsewhere in this repo before writing this test.

```python
# backend/tests/observability/test_models.py
import uuid

from app.modules.observability.constants import LokiAuthType
from app.modules.observability.models import LokiConfig


def test_loki_config_model_columns():
    config = LokiConfig(
        id=uuid.uuid4(),
        environment_id=uuid.uuid4(),
        endpoint_url="http://loki:3100",
        tenant_id="tenant-a",
        auth_type=LokiAuthType.BEARER,
        credential="ciphertext",
        default_query='{job="api"}',
        default_range_minutes=60,
    )
    assert config.auth_type == LokiAuthType.BEARER
    assert config.default_range_minutes == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/observability/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.observability'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/observability/config.py
"""Settings owned by the observability module — the business-domain secret
only. Mirrors app/modules/cloudflare/config.py's exact split (domain secret
in the module, transport settings in the integration)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilityConfig(BaseSettings):
    """Environment driven settings for the observability module."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="OBSERVABILITY__", extra="ignore")

    # Fernet key encrypting LokiConfig.credential at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY: str = ""


observability_settings = ObservabilityConfig()
```

```python
# backend/app/modules/observability/constants.py
from enum import StrEnum


class LokiAuthType(StrEnum):
    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"


class ObservabilityLimits:
    MAX_ENDPOINT_URL_LENGTH = 2048
    MAX_TENANT_ID_LENGTH = 128
    MAX_QUERY_LENGTH = 4096
    MAX_QUERY_LIMIT = 1000
    DEFAULT_QUERY_LIMIT = 200


class ErrorCode(StrEnum):
    CONFIG_NOT_FOUND = "loki_config_not_found"
    CONFIG_ALREADY_EXISTS = "loki_config_already_exists"
    ENVIRONMENT_NOT_FOUND = "observability_environment_not_found"


class ObservabilityAuditActions(StrEnum):
    LOKI_CONFIG_CREATED = "LOKI_CONFIG_CREATED"
    LOKI_CONFIG_UPDATED = "LOKI_CONFIG_UPDATED"
    LOKI_CONFIG_DELETED = "LOKI_CONFIG_DELETED"
```

```python
# backend/app/modules/observability/models.py
"""SQLAlchemy models owned exclusively by the observability module. No other
module may query these tables directly — reach them only through
app.modules.observability.public (currently empty; add a facade method here
if a real cross-module consumer appears)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.observability.constants import LokiAuthType, ObservabilityLimits


class LokiConfig(Base):
    """A single environment's Loki connection settings. 1:1 per environment."""

    __tablename__ = "loki_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    endpoint_url: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[str | None] = mapped_column(String(ObservabilityLimits.MAX_TENANT_ID_LENGTH), nullable=True)
    auth_type: Mapped[LokiAuthType] = mapped_column(Enum(LokiAuthType, native_enum=False))
    credential: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_query: Mapped[str] = mapped_column(Text, default="")
    default_range_minutes: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

Confirm the exact `Base` import path (`app.core.database` is a placeholder guess — read `app/modules/cloudflare/models.py`'s real import line first and use that exact path) before finalizing this file.

```python
# backend/app/modules/observability/schemas.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.integrations.loki.schemas import LokiLogEntry
from app.modules.observability.constants import LokiAuthType, ObservabilityLimits


class LokiConfigRead(BaseModel):
    id: UUID
    environment_id: UUID
    endpoint_url: str
    tenant_id: str | None
    auth_type: LokiAuthType
    has_credential: bool
    default_query: str
    default_range_minutes: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LokiConfigCreate(BaseModel):
    endpoint_url: str = Field(max_length=ObservabilityLimits.MAX_ENDPOINT_URL_LENGTH)
    tenant_id: str | None = Field(default=None, max_length=ObservabilityLimits.MAX_TENANT_ID_LENGTH)
    auth_type: LokiAuthType
    credential: str | None = None
    default_query: str = Field(default="", max_length=ObservabilityLimits.MAX_QUERY_LENGTH)
    default_range_minutes: int = 60


class LokiConfigUpdate(BaseModel):
    endpoint_url: str | None = Field(default=None, max_length=ObservabilityLimits.MAX_ENDPOINT_URL_LENGTH)
    tenant_id: str | None = Field(default=None, max_length=ObservabilityLimits.MAX_TENANT_ID_LENGTH)
    auth_type: LokiAuthType | None = None
    credential: str | None = None
    default_query: str | None = Field(default=None, max_length=ObservabilityLimits.MAX_QUERY_LENGTH)
    default_range_minutes: int | None = None


class LogQueryRequest(BaseModel):
    query: str = Field(max_length=ObservabilityLimits.MAX_QUERY_LENGTH)
    start: datetime
    end: datetime
    limit: int = ObservabilityLimits.DEFAULT_QUERY_LIMIT


class LogQueryResponse(BaseModel):
    entries: list[LokiLogEntry]
```

```python
# backend/app/modules/observability/exceptions.py
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.observability.constants import ErrorCode


class LokiConfigNotFound(NotFoundError):
    code = ErrorCode.CONFIG_NOT_FOUND
    message = "Loki config not found for this environment"


class LokiConfigAlreadyExists(ConflictError):
    code = ErrorCode.CONFIG_ALREADY_EXISTS
    message = "A Loki config already exists for this environment"


class ObservabilityEnvironmentNotFound(NotFoundError):
    code = ErrorCode.ENVIRONMENT_NOT_FOUND
    message = "Environment not found"
```

Confirm the exact base exception class names (`NotFoundError`/`ConflictError`) and their constructor kwargs by reading `app/modules/cloudflare/exceptions.py`'s equivalent `CloudflareConfigNotFound`/`CloudflareConfigAlreadyExists` classes first — mirror those exactly rather than guessing the base class names.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/observability
git commit -m "feat(observability): add module scaffold (config, constants, models, schemas, exceptions)"
```

---

## Task 5: Alembic migration for `loki_configs`

**Files:**
- Create: `backend/alembic/versions/<generated>_create_loki_configs_schema.py`

**Interfaces:**
- Consumes: `LokiConfig` model (Task 4).
- Produces: `loki_configs` table in `itsm_test`.

- [ ] **Step 1: Generate the migration**

Run: `cd backend && uv run alembic revision --autogenerate -m "create loki_configs schema"`

- [ ] **Step 2: Verify the generated migration**

Open the generated file. Confirm:
- `down_revision = "f3a8c1d9e4b7"` (the current head confirmed during research — if autogenerate produced a different value, the head moved since this plan was written; stop and re-check `alembic heads` before proceeding).
- `auth_type` column uses `sa.Enum(..., native_enum=False)`, matching every prior migration's convention — autogenerate may emit a native Postgres enum instead; if so, manually edit to add `native_enum=False`.
- `environment_id` has both `unique=True` and a `ForeignKey(..., ondelete="CASCADE")` reflected correctly in the `op.create_table(...)` call.

- [ ] **Step 3: Apply to `itsm_test`**

Run: `cd backend && DATABASE_URL=<itsm_test connection string> uv run alembic upgrade head`
Expected: migration applies cleanly, no errors. **Never run this against `business-chatbot-postgres`'s live `itsm` database.**

- [ ] **Step 4: Verify `alembic downgrade` works**

Run: `cd backend && DATABASE_URL=<itsm_test connection string> uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: both directions succeed without error, confirming the migration is reversible.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(observability): add loki_configs migration"
```

---

## Task 6: `observability/repository.py` + `uow.py`

**Files:**
- Create: `backend/app/modules/observability/repository.py`
- Create: `backend/app/modules/observability/uow.py`
- Test: `backend/tests/observability/test_repository.py`

**Interfaces:**
- Consumes: `LokiConfig` (Task 4), the `_session` real-Postgres repository-test fixture pattern from `backend/tests/cloudflare/test_repository.py` — read that file first and copy its fixture setup exactly.
- Produces: `AbstractLokiConfigRepository` (`get_by_environment_id`, `create`, `update`, `delete`), `LokiConfigRepository`, `AbstractObservabilityUnitOfWork`, `ObservabilityUnitOfWork` (real), `FakeObservabilityUnitOfWork` (for service-layer unit tests in later tasks).

- [ ] **Step 1: Write the failing test**

Read `backend/tests/cloudflare/test_repository.py` in full first and mirror its exact fixture/session pattern (do not invent a different one). Then:

```python
# backend/tests/observability/test_repository.py
import uuid

import pytest

from app.modules.observability.constants import LokiAuthType
from app.modules.observability.models import LokiConfig
from app.modules.observability.repository import LokiConfigRepository


@pytest.mark.asyncio
async def test_create_and_get_by_environment_id(session):  # fixture name TBD — match test_repository.py's real fixture name
    repo = LokiConfigRepository(session)
    environment_id = uuid.uuid4()  # must reference a real seeded environment row per this repo's FK-integrity test convention — check test_repository.py for how it seeds a parent row first
    config = LokiConfig(
        id=uuid.uuid4(),
        environment_id=environment_id,
        endpoint_url="http://loki:3100",
        auth_type=LokiAuthType.NONE,
        default_query="",
        default_range_minutes=60,
    )
    await repo.create(config)
    await session.commit()

    fetched = await repo.get_by_environment_id(environment_id)
    assert fetched is not None
    assert fetched.endpoint_url == "http://loki:3100"


@pytest.mark.asyncio
async def test_get_by_environment_id_returns_none_when_absent(session):
    repo = LokiConfigRepository(session)
    assert await repo.get_by_environment_id(uuid.uuid4()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/observability/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.observability.repository'`

- [ ] **Step 3: Write the implementation**

Read `backend/app/modules/cloudflare/repository.py`'s `AbstractCloudflareConfigRepository`/`CloudflareConfigRepository` pair (the closest 1:1-per-environment precedent) and mirror its exact shape:

```python
# backend/app/modules/observability/repository.py
from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observability.models import LokiConfig


class AbstractLokiConfigRepository(ABC):
    @abstractmethod
    async def get_by_environment_id(self, environment_id: UUID) -> LokiConfig | None: ...

    @abstractmethod
    async def create(self, config: LokiConfig) -> None: ...

    @abstractmethod
    async def update(self, config: LokiConfig) -> None: ...

    @abstractmethod
    async def delete(self, config: LokiConfig) -> None: ...


class LokiConfigRepository(AbstractLokiConfigRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_environment_id(self, environment_id: UUID) -> LokiConfig | None:
        result = await self._session.execute(select(LokiConfig).where(LokiConfig.environment_id == environment_id))
        return result.scalar_one_or_none()

    async def create(self, config: LokiConfig) -> None:
        self._session.add(config)
        await self._session.flush()

    async def update(self, config: LokiConfig) -> None:
        await self._session.flush()

    async def delete(self, config: LokiConfig) -> None:
        await self._session.delete(config)
        await self._session.flush()
```

```python
# backend/app/modules/observability/uow.py
```

Copy `backend/app/modules/cloudflare/uow.py`'s exact `AbstractCloudflareUnitOfWork`/`CloudflareUnitOfWork` structure (commit/rollback/`__aenter__`/`__aexit__` pattern), substituting a single `.loki_configs: AbstractLokiConfigRepository` property in place of `.accounts`/`.account_managers`/`.configs`/`.dns_records`/`.tunnels`/`.tunnel_hostnames`. Also add a `FakeObservabilityUnitOfWork` in a new `backend/tests/observability/fakes.py`, mirroring whatever `FakeCloudflareUnitOfWork` fixture file cloudflare's tests use (read it first) — an in-memory dict-backed fake for Task 7's service-layer unit tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/observability/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/observability/repository.py backend/app/modules/observability/uow.py backend/tests/observability/
git commit -m "feat(observability): add repository and unit of work"
```

---

## Task 7: `.importlinter` — `observability-facade` + source_modules additions

**Files:**
- Modify: `backend/.importlinter`

**Interfaces:**
- Consumes: none (config file only).
- Produces: `observability-facade` contract; `app.modules.observability` added to `rbac-facade`, `users-facade`, `projects-facade`, `audit-facade` source_modules.

- [ ] **Step 1: Edit `.importlinter`**

Add `app.modules.observability` to the `source_modules` list of these 4 existing contracts (same treatment `app.modules.cloudflare` got in Phase 3): `rbac-facade`, `users-facade`, `projects-facade`, `audit-facade`.

Add a new stanza (mirrors `cloudflare-facade`'s exact shape):

```ini
[importlinter:contract:observability-facade]
name = Other modules reach observability only through public.py
type = forbidden
source_modules =
    app.modules.auth
    app.modules.rbac
    app.modules.users
    app.modules.projects
    app.modules.audit
    app.modules.cloudflare
    app.modules.common
forbidden_modules =
    app.modules.observability.repository
    app.modules.observability.models
    app.modules.observability.uow
    app.modules.observability.services
allow_indirect_imports = True
```

Also add `app.integrations.loki` to the `integrations-are-leaves` contract's `source_modules` list (alongside `app.integrations.cloudflare` etc.) and to `root-is-mechanism`'s `forbidden_modules` list, mirroring exactly how `app.integrations.cloudflare` appears in both.

- [ ] **Step 2: Verify**

Run: `cd backend && lint-imports`
Expected: all contracts pass (no violations yet, since `app.modules.observability` doesn't import anything cross-module yet at this point in the plan).

- [ ] **Step 3: Commit**

```bash
git add backend/.importlinter
git commit -m "chore(importlinter): add observability-facade contract and loki integration leaf"
```

---

## Task 8: `observability/services/*.py` + `dependencies.py`

**Files:**
- Create: `backend/app/modules/observability/services/create_loki_config.py`
- Create: `backend/app/modules/observability/services/update_loki_config.py`
- Create: `backend/app/modules/observability/services/delete_loki_config.py`
- Create: `backend/app/modules/observability/services/get_loki_config.py`
- Create: `backend/app/modules/observability/services/run_log_query.py`
- Create: `backend/app/modules/observability/dependencies.py`
- Test: `backend/tests/observability/test_services.py`

**Interfaces:**
- Consumes: `AbstractObservabilityUnitOfWork`/`FakeObservabilityUnitOfWork` (Task 6), `LokiClient` (Task 2), `ProjectsApi`/`get_projects_api` (`app.modules.projects.public`), `AuditApi`/`get_audit_api` (`app.modules.audit.public`), `FernetCodec` (`app.core.crypto`), `observability_settings` (Task 4).
- Produces: `CreateLokiConfig`, `UpdateLokiConfig`, `DeleteLokiConfig`, `GetLokiConfig`, `RunLogQuery` — each with `async def execute(...)`.

- [ ] **Step 1: Write the failing tests**

Read `backend/app/modules/cloudflare/services/create_config.py` in full first (the closest precedent: validates environment exists, rejects if already bound, encrypts a secret, audits) and mirror its control flow exactly, substituting Loki's fields.

```python
# backend/tests/observability/test_services.py
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.crypto import FernetCodec
from app.modules.observability.constants import LokiAuthType
from app.modules.observability.exceptions import LokiConfigAlreadyExists, LokiConfigNotFound, ObservabilityEnvironmentNotFound
from app.modules.observability.services.create_loki_config import CreateLokiConfig
from app.modules.observability.services.run_log_query import RunLogQuery
from app.integrations.loki.schemas import LokiLogEntry, LokiQueryResult

FERNET_KEY = FernetCodec_key_for_tests = "zGX1qF3n0v6d9m2E4pP8sQ5rT7uW1yA3bC6dE9fG2hI="  # any valid Fernet key generated once for test fixtures


@pytest.mark.asyncio
async def test_create_loki_config_rejects_unknown_environment(fake_uow, fake_projects_api, fake_audit_api):
    fake_projects_api.get_environment_by_id = AsyncMock(return_value=None)
    use_case = CreateLokiConfig(fake_uow, fake_projects_api, fake_audit_api)
    with pytest.raises(ObservabilityEnvironmentNotFound):
        await use_case.execute(environment_id=uuid.uuid4(), endpoint_url="http://loki:3100", tenant_id=None, auth_type=LokiAuthType.NONE, credential=None, default_query="", default_range_minutes=60, actor_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_create_loki_config_rejects_duplicate_binding(fake_uow, fake_projects_api, fake_audit_api, seeded_environment):
    use_case = CreateLokiConfig(fake_uow, fake_projects_api, fake_audit_api)
    kwargs = dict(environment_id=seeded_environment.id, endpoint_url="http://loki:3100", tenant_id=None, auth_type=LokiAuthType.NONE, credential=None, default_query="", default_range_minutes=60, actor_id=uuid.uuid4())
    await use_case.execute(**kwargs)
    with pytest.raises(LokiConfigAlreadyExists):
        await use_case.execute(**kwargs)


@pytest.mark.asyncio
async def test_create_loki_config_encrypts_bearer_credential(fake_uow, fake_projects_api, fake_audit_api, seeded_environment):
    use_case = CreateLokiConfig(fake_uow, fake_projects_api, fake_audit_api)
    config = await use_case.execute(
        environment_id=seeded_environment.id, endpoint_url="http://loki:3100", tenant_id=None,
        auth_type=LokiAuthType.BEARER, credential="raw-token", default_query="", default_range_minutes=60,
        actor_id=uuid.uuid4(),
    )
    assert config.credential != "raw-token"  # stored ciphertext, never plaintext


@pytest.mark.asyncio
async def test_run_log_query_builds_basic_auth_header(fake_uow, fake_loki_client, seeded_loki_config_basic_auth):
    use_case = RunLogQuery(fake_uow, fake_loki_client)
    await use_case.execute(
        environment_id=seeded_loki_config_basic_auth.environment_id,
        query='{job="api"}', start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, 1, tzinfo=UTC), limit=100,
    )
    call_kwargs = fake_loki_client.query_range.call_args.kwargs
    assert call_kwargs["auth_header"].startswith("Basic ")


@pytest.mark.asyncio
async def test_run_log_query_rejects_missing_config(fake_uow, fake_loki_client):
    use_case = RunLogQuery(fake_uow, fake_loki_client)
    with pytest.raises(LokiConfigNotFound):
        await use_case.execute(environment_id=uuid.uuid4(), query="{}", start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, 1, tzinfo=UTC), limit=100)


@pytest.mark.asyncio
async def test_run_log_query_enforces_max_limit(fake_uow, fake_loki_client, seeded_loki_config_no_auth):
    use_case = RunLogQuery(fake_uow, fake_loki_client)
    await use_case.execute(
        environment_id=seeded_loki_config_no_auth.environment_id, query="{}",
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, 1, tzinfo=UTC), limit=999_999,
    )
    call_kwargs = fake_loki_client.query_range.call_args.kwargs
    assert call_kwargs["limit"] <= 1000  # ObservabilityLimits.MAX_QUERY_LIMIT, clamped not rejected
```

The `fake_uow`/`fake_projects_api`/`fake_audit_api`/`fake_loki_client`/`seeded_environment`/`seeded_loki_config_*` fixtures need real definitions in a `backend/tests/observability/conftest.py` — read `backend/tests/cloudflare/conftest.py` first and mirror its exact fixture-construction style (do not invent a divergent pattern) before finalizing these test bodies; the exact fixture signatures above are illustrative of intent, adjust argument names to match whatever convention `tests/cloudflare/conftest.py` already establishes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/observability/services/create_loki_config.py
from uuid import UUID

from app.core.crypto import FernetCodec
from app.modules.audit.public import AuditActor, AuditApi, AuditEventType, AuditSeverity, AuditSource
from app.modules.observability.config import observability_settings
from app.modules.observability.constants import LokiAuthType, ObservabilityAuditActions
from app.modules.observability.exceptions import LokiConfigAlreadyExists, ObservabilityEnvironmentNotFound
from app.modules.observability.models import LokiConfig
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
from app.modules.projects.public import ProjectsApi

import uuid as uuid_module


class CreateLokiConfig:
    def __init__(self, uow: AbstractObservabilityUnitOfWork, projects_api: ProjectsApi, audit_api: AuditApi) -> None:
        self._uow = uow
        self._projects_api = projects_api
        self._audit_api = audit_api

    async def execute(
        self,
        *,
        environment_id: UUID,
        endpoint_url: str,
        tenant_id: str | None,
        auth_type: LokiAuthType,
        credential: str | None,
        default_query: str,
        default_range_minutes: int,
        actor_id: UUID,
    ) -> LokiConfig:
        if await self._projects_api.get_environment_by_id(environment_id) is None:
            raise ObservabilityEnvironmentNotFound()

        async with self._uow:
            if await self._uow.loki_configs.get_by_environment_id(environment_id) is not None:
                raise LokiConfigAlreadyExists()

            ciphertext = None
            if credential is not None:
                ciphertext = FernetCodec.encrypt(credential, key=observability_settings.FERNET_KEY)

            config = LokiConfig(
                id=uuid_module.uuid4(),
                environment_id=environment_id,
                endpoint_url=endpoint_url,
                tenant_id=tenant_id,
                auth_type=auth_type,
                credential=ciphertext,
                default_query=default_query,
                default_range_minutes=default_range_minutes,
            )
            await self._uow.loki_configs.create(config)
            await self._uow.commit()

        await self._audit_api.log_event(
            type=AuditEventType.CONFIG_CHANGE,
            source=AuditSource.SYSTEM,
            action=ObservabilityAuditActions.LOKI_CONFIG_CREATED,
            severity=AuditSeverity.INFO,
            message=f"Loki config created for environment {environment_id}",
            actor=AuditActor(id=actor_id),
            environment_id=environment_id,
        )
        return config
```

Confirm the exact `AuditActor`/`AuditEventType`/`AuditSource`/`AuditSeverity` import path and constructor shape by reading `app/modules/cloudflare/services/create_config.py`'s real audit-log call first — the names/types above are best-effort from the Task-4-adjacent research and must be verified against the actual `app/modules/audit/public.py` `__all__` list before this compiles.

```python
# backend/app/modules/observability/services/get_loki_config.py
from uuid import UUID

from app.modules.observability.exceptions import LokiConfigNotFound
from app.modules.observability.models import LokiConfig
from app.modules.observability.uow import AbstractObservabilityUnitOfWork


class GetLokiConfig:
    def __init__(self, uow: AbstractObservabilityUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, environment_id: UUID) -> LokiConfig:
        async with self._uow:
            config = await self._uow.loki_configs.get_by_environment_id(environment_id)
        if config is None:
            raise LokiConfigNotFound()
        return config
```

```python
# backend/app/modules/observability/services/update_loki_config.py
```
Mirror `app/modules/cloudflare/services/update_config.py` exactly: load-by-environment_id (404 via `LokiConfigNotFound` if absent), apply only the non-`None` fields from `LokiConfigUpdate`, re-encrypt `credential` if a new plaintext value was supplied (never re-encrypt if the field was omitted — omission means "leave the existing secret alone," matching how `UpdateCloudflareAccount` treats a not-provided `api_token`), commit, audit `LOKI_CONFIG_UPDATED`.

```python
# backend/app/modules/observability/services/delete_loki_config.py
```
Mirror `app/modules/cloudflare/services/delete_config.py`'s structure minus its DNS-records-exist guard (no equivalent dependent-row concept here — `loki_configs` has nothing depending on it): load-by-environment_id (404 if absent), delete, commit, audit `LOKI_CONFIG_DELETED`.

```python
# backend/app/modules/observability/services/run_log_query.py
from datetime import datetime
from uuid import UUID

from app.core.crypto import FernetCodec
from app.integrations.loki.client import LokiClient
from app.integrations.loki.schemas import LokiQueryResult
from app.modules.observability.config import observability_settings
from app.modules.observability.constants import LokiAuthType, ObservabilityLimits
from app.modules.observability.exceptions import LokiConfigNotFound
from app.modules.observability.uow import AbstractObservabilityUnitOfWork
import base64


class RunLogQuery:
    def __init__(self, uow: AbstractObservabilityUnitOfWork, client: LokiClient) -> None:
        self._uow = uow
        self._client = client

    async def execute(
        self, *, environment_id: UUID, query: str, start: datetime, end: datetime, limit: int
    ) -> LokiQueryResult:
        async with self._uow:
            config = await self._uow.loki_configs.get_by_environment_id(environment_id)
        if config is None:
            raise LokiConfigNotFound()

        auth_header = None
        if config.auth_type == LokiAuthType.BEARER and config.credential:
            token = FernetCodec.decrypt(config.credential, key=observability_settings.FERNET_KEY)
            auth_header = f"Bearer {token}"
        elif config.auth_type == LokiAuthType.BASIC and config.credential:
            plaintext = FernetCodec.decrypt(config.credential, key=observability_settings.FERNET_KEY)
            auth_header = f"Basic {base64.b64encode(plaintext.encode()).decode()}"

        clamped_limit = min(limit, ObservabilityLimits.MAX_QUERY_LIMIT)
        return await self._client.query_range(
            endpoint_url=config.endpoint_url,
            query=query,
            start=start,
            end=end,
            tenant_id=config.tenant_id,
            auth_header=auth_header,
            limit=clamped_limit,
        )
```

```python
# backend/app/modules/observability/dependencies.py
```
Mirror `app/modules/cloudflare/dependencies.py`'s exact provider-function shape (`get_uow`, `get_create_loki_config`, `get_update_loki_config`, `get_delete_loki_config`, `get_get_loki_config`, `get_run_log_query`, `get_loki_client`) — each a plain `async def get_X(uow=Depends(get_uow), ...) -> X: return X(...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/observability/services backend/app/modules/observability/dependencies.py backend/tests/observability/
git commit -m "feat(observability): add loki config CRUD and query services"
```

---

## Task 9: `observability/router.py` + `public.py` + `main.py` registration

**Files:**
- Create: `backend/app/modules/observability/router.py`
- Create: `backend/app/modules/observability/public.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/observability/test_router.py`

**Interfaces:**
- Consumes: everything from Task 8, `require_permission` (`app.modules.rbac.public`), `RbacResources`/`RbacActions` (`app.modules.rbac.constants`), `UserRead` (`app.modules.users.public`), `ApiResponse` (read its real import path from `app/modules/cloudflare/router.py`'s import block first).
- Produces: 5 registered routes.

- [ ] **Step 1: Write the failing tests**

Read `backend/tests/cloudflare/test_router.py`'s `_login_with_permissions` helper in full first and reuse it exactly (do not redefine a parallel helper).

```python
# backend/tests/observability/test_router.py
import pytest


@pytest.mark.asyncio
async def test_create_loki_config_requires_environment_update_permission(client, _login_with_permissions, seeded_environment):
    user_headers = await _login_with_permissions(client, [("environment", "read")])  # read-only, not update
    response = await client.post(
        f"/environments/{seeded_environment.id}/loki-config",
        json={"endpoint_url": "http://loki:3100", "tenant_id": None, "auth_type": "none", "credential": None, "default_query": "", "default_range_minutes": 60},
        headers=user_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_then_get_loki_config(client, _login_with_permissions, seeded_environment):
    admin_headers = await _login_with_permissions(client, [("environment", "update"), ("environment", "read")])
    create_response = await client.post(
        f"/environments/{seeded_environment.id}/loki-config",
        json={"endpoint_url": "http://loki:3100", "tenant_id": None, "auth_type": "none", "credential": None, "default_query": "{}", "default_range_minutes": 60},
        headers=admin_headers,
    )
    assert create_response.status_code in (200, 201)

    get_response = await client.get(f"/environments/{seeded_environment.id}/loki-config", headers=admin_headers)
    assert get_response.status_code == 200
    body = get_response.json()["data"]
    assert body["endpoint_url"] == "http://loki:3100"
    assert "credential" not in body  # LokiConfigRead never exposes the raw/encrypted credential
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/observability/test_router.py -v`
Expected: FAIL (404 / route not found)

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/observability/router.py
from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.observability.dependencies import (
    get_create_loki_config,
    get_delete_loki_config,
    get_get_loki_config,
    get_run_log_query,
    get_update_loki_config,
)
from app.modules.observability.schemas import (
    LogQueryRequest,
    LogQueryResponse,
    LokiConfigCreate,
    LokiConfigRead,
    LokiConfigUpdate,
)
from app.modules.rbac.constants import RbacActions, RbacResources
from app.modules.rbac.public import require_permission
from app.modules.users.public import UserRead
from app.shared.schemas import ApiResponse  # confirm real path from cloudflare/router.py's import block

router = APIRouter()


@router.post("/environments/{environment_id}/loki-config")
async def create_loki_config(
    environment_id: UUID,
    payload: LokiConfigCreate,
    use_case=Depends(get_create_loki_config),
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.UPDATE)),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id=environment_id, actor_id=user.id, **payload.model_dump())
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.get("/environments/{environment_id}/loki-config")
async def get_loki_config(
    environment_id: UUID,
    use_case=Depends(get_get_loki_config),
    _user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.READ)),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id)
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.patch("/environments/{environment_id}/loki-config")
async def update_loki_config(
    environment_id: UUID,
    payload: LokiConfigUpdate,
    use_case=Depends(get_update_loki_config),
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.UPDATE)),
) -> ApiResponse[LokiConfigRead]:
    config = await use_case.execute(environment_id=environment_id, actor_id=user.id, **payload.model_dump(exclude_unset=True))
    return ApiResponse[LokiConfigRead](success=True, data=config)


@router.delete("/environments/{environment_id}/loki-config")
async def delete_loki_config(
    environment_id: UUID,
    use_case=Depends(get_delete_loki_config),
    user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.UPDATE)),
) -> ApiResponse[None]:
    await use_case.execute(environment_id=environment_id, actor_id=user.id)
    return ApiResponse[None](success=True, data=None)


@router.post("/environments/{environment_id}/loki-config/query")
async def run_log_query(
    environment_id: UUID,
    payload: LogQueryRequest,
    use_case=Depends(get_run_log_query),
    _user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.READ)),
) -> ApiResponse[LogQueryResponse]:
    result = await use_case.execute(environment_id=environment_id, **payload.model_dump())
    return ApiResponse[LogQueryResponse](success=True, data=LogQueryResponse(entries=result.entries))
```

Note: `LokiConfigUpdate`/`LokiConfigCreate.model_dump()` must not pass a raw `credential` field name collision with the service's `credential` kwarg mismatch — verify field names line up 1:1 between `schemas.py` (Task 4) and each service's `execute(...)` signature (Task 8) before this compiles; adjust either side if they drifted during writing.

```python
# backend/app/modules/observability/public.py
"""Contract exposed to other modules. Empty for now — no cross-module
consumer needs observability data yet (Decision #1: the Cloudflare Audit
Log tab reuses cloudflare's own 2-layer ACL instead of a facade here)."""

__all__: list[str] = []
```

Register in `backend/app/main.py`: add `from app.modules.observability.router import router as observability_router` and `app.include_router(observability_router, ...)` mirroring exactly how `cloudflare_router`/`audit_router` are registered there — read the existing registration block first and match its prefix/tags kwargs convention.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/observability/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/observability/router.py backend/app/modules/observability/public.py backend/app/main.py backend/tests/observability/
git commit -m "feat(observability): add loki config router and register in main.py"
```

---

## Task 10: `app/modules/cloudflare/` — Audit Logs service + endpoint

**Files:**
- Create: `backend/app/modules/cloudflare/services/list_cloudflare_audit_logs.py`
- Modify: `backend/app/modules/cloudflare/router.py`
- Modify: `backend/app/modules/cloudflare/dependencies.py`
- Test: `backend/tests/cloudflare/test_services.py` (append)
- Test: `backend/tests/cloudflare/test_router.py` (append)

**Interfaces:**
- Consumes: `CloudflareClient.get_account_audit_logs` (Task 3), `AbstractCloudflareUnitOfWork` (existing), `FernetCodec`/`cloudflare_settings` (existing pattern from `list_zones.py`).
- Produces: `ListCloudflareAuditLogs.execute(environment_id, since, before) -> list[CloudflareAuditLogEntry]`, `GET /environments/{environment_id}/cloudflare-audit-logs`.

- [ ] **Step 1: Write the failing tests**

Read `backend/app/modules/cloudflare/services/list_zones.py` in full first — it's the closest precedent (resolves environment → config → account → decrypts token → calls the client) and this service's control flow should mirror it exactly up through token decryption, then diverge only for the final client call.

```python
# append to backend/tests/cloudflare/test_services.py

@pytest.mark.asyncio
async def test_list_cloudflare_audit_logs_requires_bound_environment(fake_uow, fake_client):
    use_case = ListCloudflareAuditLogs(fake_uow, fake_client)
    with pytest.raises(CloudflareConfigNotFound):
        await use_case.execute(environment_id=uuid.uuid4(), since=None, before=None)


@pytest.mark.asyncio
async def test_list_cloudflare_audit_logs_calls_client_with_zone_name(fake_uow, fake_client, seeded_config_and_account):
    use_case = ListCloudflareAuditLogs(fake_uow, fake_client)
    await use_case.execute(environment_id=seeded_config_and_account.environment_id, since=None, before=None)
    call_kwargs = fake_client.get_account_audit_logs.call_args.kwargs
    assert call_kwargs["zone_name"] == seeded_config_and_account.zone_name
```

(Fixture names `fake_uow`/`fake_client`/`seeded_config_and_account` must match whatever `tests/cloudflare/conftest.py` already defines for the DNS/Tunnel service tests — read that file first rather than inventing new fixture names.)

```python
# append to backend/tests/cloudflare/test_router.py

@pytest.mark.asyncio
async def test_cloudflare_audit_logs_requires_view_permission(client, _login_with_permissions, seeded_environment):
    headers = await _login_with_permissions(client, [])  # no permissions at all
    response = await client.get(f"/environments/{seeded_environment.id}/cloudflare-audit-logs", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cloudflare_audit_logs_404s_for_unbound_environment(client, _login_with_permissions, seeded_environment):
    headers = await _login_with_permissions(client, [("cloudflare_account", "view")])
    response = await client.get(f"/environments/{seeded_environment.id}/cloudflare-audit-logs", headers=headers)
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py tests/cloudflare/test_router.py -k audit_logs -v`
Expected: FAIL (`ImportError`/404)

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/cloudflare/services/list_cloudflare_audit_logs.py
from datetime import datetime
from uuid import UUID

from app.core.crypto import FernetCodec
from app.integrations.cloudflare.client import CloudflareClient
from app.integrations.cloudflare.schemas import CloudflareAuditLogEntry
from app.modules.cloudflare.config import cloudflare_settings
from app.modules.cloudflare.exceptions import CloudflareConfigNotFound
from app.modules.cloudflare.uow import AbstractCloudflareUnitOfWork


class ListCloudflareAuditLogs:
    def __init__(self, uow: AbstractCloudflareUnitOfWork, client: CloudflareClient) -> None:
        self._uow = uow
        self._client = client

    async def execute(
        self, *, environment_id: UUID, since: datetime | None, before: datetime | None
    ) -> list[CloudflareAuditLogEntry]:
        async with self._uow:
            config = await self._uow.configs.get_by_environment_id(environment_id)
            if config is None:
                raise CloudflareConfigNotFound()
            account = await self._uow.accounts.get_by_id(config.cloudflare_account_id)

        plaintext = FernetCodec.decrypt(account.api_token, key=cloudflare_settings.FERNET_KEY)
        return await self._client.get_account_audit_logs(
            cf_account_id=account.cf_account_id,
            api_token=plaintext,
            zone_name=config.zone_name,
            since=since,
            before=before,
        )
```

Verify the exact `account.api_token`/`account.cf_account_id` attribute names and `self._uow.accounts.get_by_id` signature against `list_zones.py`'s real code before finalizing — the names above are inferred from the Decision #7/research pass, not independently re-confirmed for this exact file.

Add to `backend/app/modules/cloudflare/router.py`:
```python
@router.get("/environments/{environment_id}/cloudflare-audit-logs")
async def list_cloudflare_audit_logs(
    environment_id: UUID,
    since: datetime | None = None,
    before: datetime | None = None,
    use_case: ListCloudflareAuditLogs = Depends(get_list_cloudflare_audit_logs),
    _l1: UserRead = Depends(require_permission(RbacResources.CLOUDFLARE_ACCOUNT, RbacActions.VIEW)),
    _grant: AccountAccessGrant = Depends(require_account_access_for_environment(AccessLevel.VIEWER)),
) -> ApiResponse[list[CloudflareAuditLogEntry]]:
    """List this environment's Cloudflare Audit Log entries, filtered to its
    bound zone. Logpull (raw traffic) was dropped from Phase 6 — Enterprise
    plan only; this is config-change history, not HTTP request logs."""
    entries = await use_case.execute(environment_id=environment_id, since=since, before=before)
    return ApiResponse[list[CloudflareAuditLogEntry]](success=True, data=entries)
```
Add a `get_list_cloudflare_audit_logs` provider to `backend/app/modules/cloudflare/dependencies.py`, mirroring the existing `get_list_zones`/`get_list_dns_records` providers' exact shape.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/cloudflare/test_services.py tests/cloudflare/test_router.py -v`
Expected: PASS (full existing suite + new tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/cloudflare/services/list_cloudflare_audit_logs.py backend/app/modules/cloudflare/router.py backend/app/modules/cloudflare/dependencies.py backend/tests/cloudflare/
git commit -m "feat(cloudflare): add environment-scoped Cloudflare Audit Logs endpoint"
```

---

## Task 11: Full backend verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q`
Expected: all green. If `check_module_boundaries.py` or `lint-imports` fails, the most likely cause is a missed `.importlinter` source_modules addition from Task 7 or a stray direct import bypassing `projects.public`/`audit.public`/`rbac.public` somewhere in Tasks 8-10 — fix the import, don't add a new exemption.

- [ ] **Step 2: Fix any failures, re-run until green**

- [ ] **Step 3: Commit if any fixes were needed**

```bash
git add -A
git commit -m "fix(observability): resolve backend verification findings"
```

---

## Task 12: Frontend — `shared/constants/api.ts` + `modules/log-viewer/` scaffolding (schema, query-keys, fetchers)

**Files:**
- Modify: `frontend/src/shared/constants/api.ts`
- Create: `frontend/src/modules/log-viewer/model/schema.ts`
- Create: `frontend/src/modules/log-viewer/api/query-keys.ts`
- Create: `frontend/src/modules/log-viewer/api/fetchers.ts`
- Test: `frontend/src/modules/log-viewer/model/schema.test.ts`

**Interfaces:**
- Consumes: `apiFetch`, `ApiRequestError` (read exact import paths from `frontend/src/modules/cloudflare-dns/api/fetchers.ts`).
- Produces: `lokiConfigSchema`, `logEntrySchema`, `cloudflareAuditLogEntrySchema` + inferred types; `logViewerKeys`; `fetchLokiConfigOrNull`, `createLokiConfig`, `updateLokiConfig`, `deleteLokiConfig`, `runLogQuery`, `fetchCloudflareAuditLogs`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/modules/log-viewer/model/schema.test.ts
import { describe, expect, it } from "vitest";
import { lokiConfigSchema, logEntrySchema } from "./schema";

describe("lokiConfigSchema", () => {
  it("parses a config without a credential field", () => {
    const parsed = lokiConfigSchema.parse({
      id: "b3f1c2e4-1111-4444-8888-000000000000",
      environmentId: "b3f1c2e4-2222-4444-8888-000000000000",
      endpointUrl: "http://loki:3100",
      tenantId: null,
      authType: "bearer",
      hasCredential: true,
      defaultQuery: '{job="api"}',
      defaultRangeMinutes: 60,
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed.hasCredential).toBe(true);
  });
});

describe("logEntrySchema", () => {
  it("parses a flattened Loki entry", () => {
    const parsed = logEntrySchema.parse({ timestamp: "1700000000000000000", line: "hello", labels: { job: "api" } });
    expect(parsed.line).toBe("hello");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/modules/log-viewer/model/schema.test.ts`
Expected: FAIL (`Cannot find module './schema'`)

- [ ] **Step 3: Write the implementation**

Read `frontend/src/modules/cloudflare-dns/model/schema.ts` in full first and mirror its exact `z.object`/field-casing (camelCase) convention.

```typescript
// frontend/src/modules/log-viewer/model/schema.ts
import { z } from "zod";

export const LOKI_AUTH_TYPES = ["none", "basic", "bearer"] as const;
export type LokiAuthType = (typeof LOKI_AUTH_TYPES)[number];

export const lokiConfigSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  endpointUrl: z.string(),
  tenantId: z.string().nullable(),
  authType: z.enum(LOKI_AUTH_TYPES),
  hasCredential: z.boolean(),
  defaultQuery: z.string(),
  defaultRangeMinutes: z.number(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type LokiConfig = z.infer<typeof lokiConfigSchema>;

export const logEntrySchema = z.object({
  timestamp: z.string(),
  line: z.string(),
  labels: z.record(z.string(), z.string()),
});
export type LogEntry = z.infer<typeof logEntrySchema>;

export const logQueryResultSchema = z.object({
  entries: z.array(logEntrySchema),
});

export const cloudflareAuditLogEntrySchema = z.object({
  id: z.string(),
  when: z.string(),
  actorEmail: z.string().nullable(),
  actorIp: z.string().nullable(),
  actionType: z.string(),
  resourceType: z.string().nullable(),
  resourceProduct: z.string().nullable(),
  newValue: z.string().nullable(),
});
export type CloudflareAuditLogEntry = z.infer<typeof cloudflareAuditLogEntrySchema>;
```

```typescript
// frontend/src/modules/log-viewer/api/query-keys.ts
export const logViewerKeys = {
  all: ["log-viewer"] as const,
  lokiConfig: (environmentId: string) => [...logViewerKeys.all, "loki-config", environmentId] as const,
  cloudflareAuditLogs: (environmentId: string, since?: string, before?: string) =>
    [...logViewerKeys.all, "cloudflare-audit-logs", environmentId, since ?? null, before ?? null] as const,
};
```

Read `frontend/src/modules/cloudflare-dns/api/fetchers.ts` in full first and mirror its exact `apiFetch<unknown>(...)` + zod-parse + `ApiRequestError`-catches-404-returns-null pattern:

```typescript
// frontend/src/modules/log-viewer/api/fetchers.ts
import { apiFetch, ApiRequestError } from "@/shared/lib/api"; // confirm exact path from cloudflare-dns/api/fetchers.ts
import { API_CONFIG } from "@/shared/constants/api";
import {
  cloudflareAuditLogEntrySchema,
  lokiConfigSchema,
  logQueryResultSchema,
  type LokiAuthType,
  type LokiConfig,
} from "../model/schema";

export async function fetchLokiConfigOrNull(environmentId: string): Promise<LokiConfig | null> {
  try {
    const data = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_CONFIG(environmentId));
    return lokiConfigSchema.parse(data);
  } catch (error) {
    if (error instanceof ApiRequestError && error.code === "loki_config_not_found") {
      return null;
    }
    throw error;
  }
}

export async function createLokiConfig(environmentId: string, payload: {
  endpointUrl: string; tenantId: string | null; authType: LokiAuthType; credential: string | null;
  defaultQuery: string; defaultRangeMinutes: number;
}): Promise<LokiConfig> {
  const data = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_CONFIG(environmentId), {
    method: "POST",
    body: JSON.stringify({
      endpoint_url: payload.endpointUrl, tenant_id: payload.tenantId, auth_type: payload.authType,
      credential: payload.credential, default_query: payload.defaultQuery, default_range_minutes: payload.defaultRangeMinutes,
    }),
  });
  return lokiConfigSchema.parse(data);
}

export async function updateLokiConfig(environmentId: string, payload: Partial<{
  endpointUrl: string; tenantId: string | null; authType: LokiAuthType; credential: string | null;
  defaultQuery: string; defaultRangeMinutes: number;
}>): Promise<LokiConfig> {
  const data = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_CONFIG(environmentId), {
    method: "PATCH",
    body: JSON.stringify({
      ...(payload.endpointUrl !== undefined && { endpoint_url: payload.endpointUrl }),
      ...(payload.tenantId !== undefined && { tenant_id: payload.tenantId }),
      ...(payload.authType !== undefined && { auth_type: payload.authType }),
      ...(payload.credential !== undefined && { credential: payload.credential }),
      ...(payload.defaultQuery !== undefined && { default_query: payload.defaultQuery }),
      ...(payload.defaultRangeMinutes !== undefined && { default_range_minutes: payload.defaultRangeMinutes }),
    }),
  });
  return lokiConfigSchema.parse(data);
}

export async function deleteLokiConfig(environmentId: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_CONFIG(environmentId), { method: "DELETE" });
}

export async function runLogQuery(environmentId: string, payload: { query: string; start: string; end: string; limit?: number }) {
  const data = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_QUERY(environmentId), {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return logQueryResultSchema.parse(data);
}

export async function fetchCloudflareAuditLogs(environmentId: string, params: { since?: string; before?: string }) {
  const search = new URLSearchParams();
  if (params.since) search.set("since", params.since);
  if (params.before) search.set("before", params.before);
  const query = search.toString();
  const path = `${API_CONFIG.ENDPOINTS.OBSERVABILITY.CLOUDFLARE_AUDIT_LOGS(environmentId)}${query ? `?${query}` : ""}`;
  const data = await apiFetch<unknown>(path);
  return cloudflareAuditLogEntrySchema.array().parse(data);
}
```

Add to `frontend/src/shared/constants/api.ts` (new top-level block, mirroring `CLOUDFLARE_DNS`'s exact shape):
```typescript
OBSERVABILITY: {
  LOKI_CONFIG: (environmentId: string) => `/environments/${environmentId}/loki-config`,
  LOKI_QUERY: (environmentId: string) => `/environments/${environmentId}/loki-config/query`,
  CLOUDFLARE_AUDIT_LOGS: (environmentId: string) => `/environments/${environmentId}/cloudflare-audit-logs`,
},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/modules/log-viewer/model/schema.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/constants/api.ts frontend/src/modules/log-viewer/model frontend/src/modules/log-viewer/api
git commit -m "feat(log-viewer): add schema, query-keys, fetchers"
```

---

## Task 13: Frontend — hooks

**Files:**
- Create: `frontend/src/modules/log-viewer/hooks/use-loki-config.ts`
- Create: `frontend/src/modules/log-viewer/hooks/use-log-query.ts`
- Create: `frontend/src/modules/log-viewer/hooks/use-cloudflare-audit-logs.ts`

**Interfaces:**
- Consumes: fetchers/keys (Task 12).
- Produces: `useLokiConfigQuery(environmentId)`, `useCreateLokiConfig()`, `useUpdateLokiConfig()`, `useDeleteLokiConfig()`, `useRunLogQuery()`, `useCloudflareAuditLogsQuery(environmentId, params)`.

- [ ] **Step 1-4: mirror `modules/cloudflare-dns/hooks/use-cloudflare-config.ts` exactly**

Read that file in full first. `useLokiConfigQuery` is a plain `useQuery` (not suspense, since "unconfigured" is a valid, common state) calling `fetchLokiConfigOrNull`, keyed by `logViewerKeys.lokiConfig(environmentId)`. `useCreateLokiConfig`/`useUpdateLokiConfig`/`useDeleteLokiConfig` are `useMutation` hooks invalidating `logViewerKeys.lokiConfig(environmentId)` on success — mirror `use-dns-records.ts`'s mutation-hook invalidation pattern exactly. `useRunLogQuery` is a `useMutation` (query results aren't cached/keyed — every "Run query" click is a fresh POST, no `useQuery` caching semantics apply to an action). `useCloudflareAuditLogsQuery` is a plain `useQuery`, keyed by `logViewerKeys.cloudflareAuditLogs(environmentId, since, before)`, `enabled: isBound` (passed in by the caller, mirroring how `useDnsRecordsQuery(environmentId, isBound)` gates on the DNS binding).

No dedicated test file for these thin hook wrappers — the existing `modules/cloudflare-dns/hooks/*` have none either (verify this is actually true by checking that directory's file list from the Task-context research before skipping tests here; if any hook file there does have a paired test, mirror that instead of skipping).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/log-viewer/hooks
git commit -m "feat(log-viewer): add loki config, query, and audit log hooks"
```

---

## Task 14: Frontend — UI (two-tab page content, config dialog) + route + i18n + nav link

**Files:**
- Create: `frontend/src/modules/log-viewer/ui/log-viewer-page-content.tsx`
- Create: `frontend/src/modules/log-viewer/ui/loki-config-form-dialog.tsx`
- Create: `frontend/src/modules/log-viewer/index.ts`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/logs/page.tsx`
- Create: `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/logs/loading.tsx`
- Modify: `frontend/src/modules/projects/ui/project-detail-view.tsx`
- Create: `frontend/locales/en/modules/log-viewer.json`
- Create: `frontend/locales/vi/modules/log-viewer.json`
- Modify: `frontend/src/shared/lib/i18n/request.ts`

**Interfaces:**
- Consumes: hooks (Task 13), `useEnvironmentQuery` (`@/entities/environment`), `useCloudflareConfigQuery` (`@/modules/cloudflare-dns`, for the "is a zone bound" check gating the Audit Log tab), shared `Dialog`/`DialogErrorAlert` (`@/shared/ui/dialog`), `Skeleton` (`@/shared/ui/skeleton`).

- [ ] **Step 1: Invoke `ui-ux-pro-max` before writing any markup**

Run (mandatory per AGENTS.md Phase 3 rule — this is UI code):
```bash
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "log viewer table time range picker tabs" --domain ux
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "monospace log line dense table" --stack nextjs
```
Apply the results to: tab affordance (accessible `role="tablist"`/`role="tab"` or a simple gated-button pattern matching whatever `cloudflare-dns-page-content.tsx` already does for any existing tab-like UI — check first, this codebase may have no prior tab precedent, in which case build the simplest accessible pattern the search results recommend), monospace font for log lines, a loading/empty/error state for query results, and keyboard-accessible time-range inputs.

- [ ] **Step 2: Write `ui/loki-config-form-dialog.tsx`**

Mirror `frontend/src/modules/cloudflare-dns/ui/dns-record-form-dialog.tsx`'s exact structure (read it in full first): uses the shared `Dialog` primitive, a form with `endpointUrl`/`tenantId`/`authType` (select: none/basic/bearer)/`credential` (password-type input, conditionally shown/required based on `authType`)/`defaultQuery`/`defaultRangeMinutes` fields, calls `useCreateLokiConfig`/`useUpdateLokiConfig` depending on whether an existing config was passed in, surfaces errors via `DialogErrorAlert`.

- [ ] **Step 3: Write `ui/log-viewer-page-content.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useEnvironmentQuery } from "@/entities/environment";
import { useCloudflareConfigQuery } from "@/modules/cloudflare-dns";
import { useLokiConfigQuery, useCreateLokiConfig, useUpdateLokiConfig, useDeleteLokiConfig } from "../hooks/use-loki-config";
import { useRunLogQuery } from "../hooks/use-log-query";
import { useCloudflareAuditLogsQuery } from "../hooks/use-cloudflare-audit-logs";

export function LogViewerPageContent({ environmentId }: { environmentId: string }) {
  const { data: environment } = useEnvironmentQuery(environmentId);
  const { data: lokiConfig, isLoading: lokiConfigLoading } = useLokiConfigQuery(environmentId);
  const { data: cfConfig } = useCloudflareConfigQuery(environmentId);
  const isZoneBound = Boolean(cfConfig);
  const [activeTab, setActiveTab] = useState<"loki" | "cloudflare">("loki");

  // ... unconfigured-Loki empty state (renders LokiConfigFormDialog trigger) vs.
  // configured state (two-tab view: LogQL query form + results table; Cloudflare
  // Audit Log tab disabled/hidden with an explanatory message when !isZoneBound)
  // — exact JSX finalized during implementation per the ui-ux-pro-max guidance
  // gathered in Step 1, following cloudflare-dns-page-content.tsx's overall
  // structure (environment header, bound/unbound branch, action buttons) as
  // the layout precedent to adapt rather than invent from scratch.
}
```

This step's final JSX must be written against the real `ui-ux-pro-max` search output from Step 1 and the real hook names from Task 13 — do not treat the skeleton above as final, it marks structure and data-flow only.

- [ ] **Step 4: Write route + loading.tsx**

Mirror `frontend/src/app/[locale]/(dashboard)/admin/environments/[environmentId]/dns/page.tsx` exactly (Server Component, SSR-prefetch only `environmentsKeys.detail(environmentId)`, gate via `hasPermission(session, RESOURCES.ENVIRONMENT, ACTIONS.READ)` — **not** `RESOURCES.CLOUDFLARE_ACCOUNT`, per Decision #2/the master-plan correction — wrap in `RequirePermission resource={RESOURCES.ENVIRONMENT} action={ACTIONS.READ}`). `loading.tsx` mirrors the DNS route's skeleton shape.

- [ ] **Step 5: Add the nav link in `project-detail-view.tsx`**

```tsx
<Can I={ACTIONS.READ} a={RESOURCES.ENVIRONMENT}>
  <Link
    href={`/admin/environments/${env.id}/logs`}
    className="text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    aria-label={t("actions.manageLogs")}
  >
    <ScrollText className="size-3.5" />
  </Link>
</Can>
```
Placed alongside the existing DNS (`Globe`)/Tunnels (`Waypoints`) icon-links, same chip. `ScrollText` from `lucide-react` (or whatever `ui-ux-pro-max`'s icon-domain search in Step 1 recommends instead, if it suggests a more fitting icon — check `--domain icons "log viewer" `before finalizing).

- [ ] **Step 6: i18n**

Create `frontend/locales/{en,vi}/modules/log-viewer.json` with keys for the config dialog fields, tab labels, empty states, and `actions.manageLogs`. Register in `shared/lib/i18n/request.ts` exactly like every other module's locale file is registered there (read the existing import list first, add this module's entry in the same alphabetical/grouped position).

- [ ] **Step 7: `index.ts`**

```typescript
export { LogViewerPageContent } from "./ui/log-viewer-page-content";
```

- [ ] **Step 8: Manual verification**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Then start the dev server and manually exercise: unconfigured environment → config dialog → configure with `auth_type=none` → run default query → (expect a connection error against a fake/no Loki instance, verify the error surfaces cleanly, not a crash) → switch to Cloudflare Audit Log tab on a zone-bound environment → verify it loads or shows a clean empty state → on an unbound environment, verify the tab shows the "no zone bound" message instead of erroring.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/modules/log-viewer frontend/src/app/\[locale\]/\(dashboard\)/admin/environments/\[environmentId\]/logs frontend/src/modules/projects/ui/project-detail-view.tsx frontend/locales frontend/src/shared/lib/i18n/request.ts
git commit -m "feat(log-viewer): add two-tab log viewer UI, route, and nav link"
```

---

## Task 15: GitNexus + skills review + finish branch

**Files:** none (verification + branch lifecycle only).

- [ ] **Step 1: Re-index and review impact**

```bash
node .gitnexus/run.cjs analyze
```
Then, if the `detect_changes`/`check` MCP tools are exposed this session, run `detect_changes({scope: "all"})` and `check()` and compare against this plan's Architecture Impact section. If not exposed, run `git diff develop..feature/loki-log-viewer --stat` and manually confirm no file outside the planned list was touched.

- [ ] **Step 2: Full verification, both stacks**

```bash
cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q
cd ../frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build
```

- [ ] **Step 3: `reviewing-code-against-skills` checklist**

Run the skill against the full branch diff. Fix loop: max 2 rounds for architectural findings, unlimited for mechanical/lint findings, per the skill's own rules.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch. Present the standard 3-option menu (base branch `develop`). On "Merge back to develop locally": merge `--no-ff`, re-run both verification commands from Step 2 against the merged result, delete the branch only after both pass.
