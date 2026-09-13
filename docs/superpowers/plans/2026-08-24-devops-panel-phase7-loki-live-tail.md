# DevOps Panel Phase 7 — Loki Live Tail (SSE)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Live" toggle to Phase 6's Loki query tab that streams new log lines via Server-Sent Events, bridging Loki's WebSocket `/tail` endpoint on the backend. One-directional stream (server pushes), matches SSE exactly — no browser-side WebSocket, no new frontend dependency.

**Architecture:** `LokiClient.tail(...)` — a new async-generator integration method connecting to Loki's `/tail` via the `websockets` library. `StreamLogTail` use case wraps it with the same permission gating as `RunLogQuery`. A new SSE router endpoint (`sse_starlette.EventSourceResponse`) bridges it to the browser, following this repo's own documented SSE pattern (`fastapi-modular-scaffold/references/api-contract.md` lines 36-53) verbatim. Frontend: a hook wrapping native `EventSource`, wired into a Live/Pause toggle in the existing Loki query tab.

**Tech Stack:** `websockets==17.0.1` (now a direct dependency, previously transitive-only via `uvicorn[standard]`), `sse-starlette==3.4.8` (new dependency), native browser `EventSource` (no new frontend package).

**Spec:** The "Phase 7 — Detailed Plan: Live tailing (SSE, not WebSocket, on the browser leg)" section of `/Users/hoangdieu/.claude/plans/rosy-juggling-pine.md` (8 numbered Decisions, all verified directly against the installed library versions in this environment, not assumed).

## Global Constraints

- `LokiClient.tail` is an async generator, `@integration`-marked like every other client method (Decision #1).
- WebSocket handshake errors map to the same 3 exceptions `query_range` already defines: `InvalidStatus` with status in (401, 403) → `InvalidLokiCredential`; other `InvalidStatus` → `LokiQueryRejected`; `OSError`/other `WebSocketException` → `LokiApiUnavailable` (Decision #2). No new exception classes.
- `resolve_loki_auth_header(config, ciphertext)` is extracted as a shared pure helper in `app/modules/observability/services/_auth.py`, used by both `RunLogQuery` (refactored) and the new `StreamLogTail` (Decision #3).
- `StreamLogTail` is gated identically to `RunLogQuery`: `RbacResources.ENVIRONMENT` / `RbacActions.READ`, no 2-layer ACL (Decision #4).
- SSE failure-mid-stream contract: yield one final `ApiResponse(success=false, error=...)` event, never close silently — per `api-contract.md` (Decision #5).
- `EventSourceResponse` gets an explicit `X-Accel-Buffering: no` header (Decision #6).
- Client disconnect closes the upstream WebSocket structurally via `GeneratorExit` propagating through `async with websockets.connect(...)` — no manual `try/finally` needed (Decision #7).
- No `start`/`delay_for`/backfill params exposed — tail always starts from "now" (Decision #8).
- Frontend caps the live-tail buffer at the last 500 entries to bound memory growth on a long-running session (disclosed limitation, not a bug).
- Router thinness (rule #10) and class-scoped constants (rule #16) apply throughout, exactly as every prior phase.

---

## Task 1: `LokiClient.tail`

**Files:**
- Modify: `backend/app/integrations/loki/client.py`
- Test: `backend/tests/integrations/loki/test_client.py` (append)

**Interfaces:**
- Consumes: `LokiApiUnavailable`, `InvalidLokiCredential`, `LokiQueryRejected` (existing, Task 1 of Phase 6), `LokiLogEntry` (existing).
- Produces: `LokiClient.tail(self, *, endpoint_url: str, query: str, tenant_id: str | None, auth_header: str | None, limit: int = 100) -> AsyncIterator[LokiLogEntry]`.

- [ ] **Step 1: Write the failing tests**

`websockets` ships a test server helper (`websockets.asyncio.server.serve`) that is the most faithful way to test a real client against a real (local, in-process) WebSocket server — more faithful than mocking `websockets.connect` internals, and avoids coupling the test to the client library's internal call shape. Read `backend/tests/integrations/loki/test_client.py`'s existing `TestQueryRange` class structure first (already in the file from Phase 6) and add a new `TestTail` class below it, using this fixture pattern:

```python
# append to backend/tests/integrations/loki/test_client.py
import asyncio
import contextlib
import json

from websockets.asyncio.server import serve as ws_serve
from websockets.exceptions import ConnectionClosedOK

from app.integrations.loki.client import LokiClient
from app.integrations.loki.exceptions import InvalidLokiCredential, LokiApiUnavailable, LokiQueryRejected
from app.integrations.loki.schemas import LokiLogEntry


class TestTail:
    async def test_streams_flattened_entries(self) -> None:
        received_headers: dict = {}

        async def handler(websocket):
            received_headers.update(websocket.request.headers)
            await websocket.send(
                json.dumps(
                    {
                        "streams": [
                            {"stream": {"job": "api"}, "values": [["1700000001000000000", "first"]]},
                        ],
                        "dropped_entries": None,
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "streams": [
                            {"stream": {"job": "api"}, "values": [["1700000002000000000", "second"]]},
                        ],
                        "dropped_entries": None,
                    }
                )
            )
            await asyncio.sleep(0.05)

        async with ws_serve(handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            client = LokiClient()
            entries: list[LokiLogEntry] = []
            with contextlib.suppress(ConnectionClosedOK):
                async for entry in client.tail(
                    endpoint_url=f"http://localhost:{port}",
                    query='{job="api"}',
                    tenant_id="tenant-a",
                    auth_header="Bearer tok",
                    limit=10,
                ):
                    entries.append(entry)
                    if len(entries) == 2:
                        break

        assert [e.line for e in entries] == ["first", "second"]
        assert received_headers.get("authorization") == "Bearer tok"
        assert received_headers.get("x-scope-orgid") == "tenant-a"

    async def test_401_handshake_raises_invalid_credential(self) -> None:
        async def handler(websocket):
            pass  # unreachable — process_request rejects before this runs

        async def process_request(connection, request):
            from websockets.http11 import Response

            return Response(401, "Unauthorized", websockets.datastructures.Headers())

        import websockets

        async with ws_serve(handler, "localhost", 0, process_request=process_request) as server:
            port = server.sockets[0].getsockname()[1]
            client = LokiClient()
            with pytest.raises(InvalidLokiCredential):
                async for _ in client.tail(
                    endpoint_url=f"http://localhost:{port}", query="{}", tenant_id=None, auth_header=None
                ):
                    pass

    async def test_connection_refused_raises_unavailable(self) -> None:
        client = LokiClient()
        with pytest.raises(LokiApiUnavailable):
            async for _ in client.tail(
                endpoint_url="http://localhost:1", query="{}", tenant_id=None, auth_header=None
            ):
                pass
```

The `test_401_handshake_raises_invalid_credential` test's exact `process_request`/`Response` construction must be verified against the real installed `websockets==17.0.1` server API during implementation — the shape above is best-effort from the library's documented hook, not independently re-confirmed the way Task 1's client-side APIs were. If the real signature differs, adjust the test to match reality rather than the client implementation to match a wrong test. `test_connection_refused_raises_unavailable` uses port 1 (a privileged, almost-certainly-closed port) as a reliable "nothing is listening" target without needing a real unreachable host (avoids DNS-timeout flakiness in CI).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integrations/loki/test_client.py -k Tail -v`
Expected: FAIL with `AttributeError: 'LokiClient' object has no attribute 'tail'`

- [ ] **Step 3: Write the implementation**

```python
# add to backend/app/integrations/loki/client.py

import json
from collections.abc import AsyncIterator

import websockets
from websockets.exceptions import InvalidStatus, WebSocketException

# ... alongside the existing imports at the top of the file

    @integration
    async def tail(
        self,
        *,
        endpoint_url: str,
        query: str,
        tenant_id: str | None,
        auth_header: str | None,
        limit: int = 100,
    ) -> AsyncIterator[LokiLogEntry]:
        """GET {endpoint_url}/loki/api/v1/tail (WebSocket, not HTTP — Loki's
        tail endpoint has no HTTP fallback). Converts the http(s) scheme to
        ws(s) before connecting. Starts from "now" — no start/delay_for
        params exposed (Decision #8). Yields entries as they arrive; never
        returns until the connection closes or the caller stops iterating."""
        ws_url = endpoint_url.replace("https://", "wss://").replace("http://", "ws://")
        query_string = f"query={query}&limit={limit}"
        uri = f"{ws_url}/loki/api/v1/tail?{query_string}"

        headers: dict[str, str] = {}
        if auth_header is not None:
            headers["Authorization"] = auth_header
        if tenant_id is not None:
            headers["X-Scope-OrgID"] = tenant_id

        try:
            async with websockets.connect(uri, additional_headers=headers) as ws:
                async for message in ws:
                    body = json.loads(message)
                    for stream in body.get("streams", []):
                        labels = stream.get("stream", {})
                        for ts, line in stream.get("values", []):
                            yield LokiLogEntry(timestamp=ts, line=line, labels=labels)
        except InvalidStatus as exc:
            if exc.response.status_code in (401, 403):
                raise InvalidLokiCredential() from exc
            raise LokiQueryRejected() from exc
        except WebSocketException as exc:
            raise LokiApiUnavailable() from exc
        except OSError as exc:
            raise LokiApiUnavailable() from exc
```

Note `query`/`limit` are placed directly into the URL query string rather than passed through `urlencode` + a `params=` kwarg the way `httpx` calls elsewhere in this codebase do — `websockets.connect` takes a bare URI string with no separate params mechanism, so the LogQL `query` value must be percent-encoded manually (`urllib.parse.quote`) before insertion to avoid breaking the URL on any `{`/`"`/space characters LogQL selectors commonly contain. Use `from urllib.parse import quote` and `query_string = f"query={quote(query)}&limit={limit}"` — the plan sketch above omits this encoding step; add it during implementation, don't ship the unencoded version.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integrations/loki/test_client.py -v`
Expected: PASS (all existing Phase 6 tests + new Tail tests)

- [ ] **Step 5: Commit**

```bash
git add app/integrations/loki/client.py tests/integrations/loki/test_client.py
git commit -m "feat(loki): add LokiClient.tail for live-tail WebSocket streaming"
```

---

## Task 2: Extract `resolve_loki_auth_header`

**Files:**
- Create: `backend/app/modules/observability/services/_auth.py`
- Modify: `backend/app/modules/observability/services/run_log_query.py`
- Test: `backend/tests/observability/test_services.py` (append a direct unit test for the extracted function; existing `TestRunLogQuery` tests must keep passing unmodified)

**Interfaces:**
- Consumes: `LokiConfigRead` (existing), `LokiAuthType` (existing), `FernetCodec`, `observability_settings`.
- Produces: `resolve_loki_auth_header(config: LokiConfigRead, ciphertext: str | None) -> str | None`.

- [ ] **Step 1: Write the failing test**

Read `run_log_query.py`'s current inline auth-header logic first (from Phase 6) — this task moves that logic verbatim into the new function, it does not redesign it.

```python
# append to backend/tests/observability/test_services.py

from app.modules.observability.services._auth import resolve_loki_auth_header


class TestResolveLokiAuthHeader:
    def test_none_auth_type_returns_none(self) -> None:
        config = LokiConfigRead(
            id=uuid4(), environment_id=uuid4(), endpoint_url="http://loki:3100", tenant_id=None,
            auth_type=LokiAuthType.NONE, has_credential=False, default_query="", default_range_minutes=60,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        assert resolve_loki_auth_header(config, None) is None

    def test_bearer_builds_header(self) -> None:
        config = LokiConfigRead(
            id=uuid4(), environment_id=uuid4(), endpoint_url="http://loki:3100", tenant_id=None,
            auth_type=LokiAuthType.BEARER, has_credential=True, default_query="", default_range_minutes=60,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        ciphertext = FernetCodec.encrypt("tok", key=TEST_FERNET_KEY)
        assert resolve_loki_auth_header(config, ciphertext) == "Bearer tok"

    def test_basic_builds_base64_header(self) -> None:
        config = LokiConfigRead(
            id=uuid4(), environment_id=uuid4(), endpoint_url="http://loki:3100", tenant_id=None,
            auth_type=LokiAuthType.BASIC, has_credential=True, default_query="", default_range_minutes=60,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        ciphertext = FernetCodec.encrypt("user:pass", key=TEST_FERNET_KEY)
        header = resolve_loki_auth_header(config, ciphertext)
        assert header is not None and header.startswith("Basic ")

    def test_missing_ciphertext_returns_none_even_if_auth_type_set(self) -> None:
        config = LokiConfigRead(
            id=uuid4(), environment_id=uuid4(), endpoint_url="http://loki:3100", tenant_id=None,
            auth_type=LokiAuthType.BEARER, has_credential=False, default_query="", default_range_minutes=60,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        assert resolve_loki_auth_header(config, None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/observability/test_services.py -k ResolveLokiAuthHeader -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.observability.services._auth'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/observability/services/_auth.py
"""Internal helper shared by RunLogQuery and StreamLogTail — not a use case
itself (no @use_case marker), never imported outside services/."""

import base64

from app.core.crypto import FernetCodec
from app.modules.observability.config import observability_settings
from app.modules.observability.constants import LokiAuthType
from app.modules.observability.schemas import LokiConfigRead


def resolve_loki_auth_header(config: LokiConfigRead, ciphertext: str | None) -> str | None:
    """Builds the fully-formed Authorization header value for a Loki
    request, or None for no auth. Returns None whenever no ciphertext is on
    hand, even if auth_type suggests one should exist — the caller (a
    repository read) is the source of truth for whether a credential is
    actually stored, not this function."""
    if config.auth_type == LokiAuthType.NONE or ciphertext is None:
        return None
    plaintext = FernetCodec.decrypt(ciphertext, key=observability_settings.FERNET_KEY)
    if config.auth_type == LokiAuthType.BEARER:
        return f"Bearer {plaintext}"
    if config.auth_type == LokiAuthType.BASIC:
        return f"Basic {base64.b64encode(plaintext.encode()).decode()}"
    return None
```

Modify `run_log_query.py`'s `execute` method: replace its inline `if config.auth_type == LokiAuthType.BEARER and config.credential: ...` block (from Phase 6) with:
```python
        ciphertext = await self._uow.loki_configs.get_credential_ciphertext(environment_id)
        auth_header = resolve_loki_auth_header(config, ciphertext)
```
removing the now-redundant `base64`/inline branching from that file, and adding `from app.modules.observability.services._auth import resolve_loki_auth_header` to its imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/observability/test_services.py -v`
Expected: PASS — the 4 new `TestResolveLokiAuthHeader` tests AND every existing `TestRunLogQuery` test from Phase 6 (unmodified assertions), proving the extraction preserved behavior exactly.

- [ ] **Step 5: Commit**

```bash
git add app/modules/observability/services/_auth.py app/modules/observability/services/run_log_query.py tests/observability/test_services.py
git commit -m "refactor(observability): extract resolve_loki_auth_header, shared by RunLogQuery and the upcoming tail service"
```

---

## Task 3: `StreamLogTail` use case + dependency provider

**Files:**
- Create: `backend/app/modules/observability/services/stream_log_tail.py`
- Modify: `backend/app/modules/observability/dependencies.py`
- Test: `backend/tests/observability/test_services.py` (append)

**Interfaces:**
- Consumes: `resolve_loki_auth_header` (Task 2), `AbstractObservabilityUnitOfWork`, `LokiClient.tail` (Task 1), `LokiConfigNotFound`.
- Produces: `StreamLogTail.execute(self, *, environment_id: UUID, query: str, limit: int) -> AsyncIterator[LokiLogEntry]`, `get_stream_log_tail` provider.

- [ ] **Step 1: Write the failing tests**

Extend `FakeLokiClient` (already in `test_services.py` from Phase 6, currently only fakes `query_range`) with a `tail` async-generator method:
```python
# modify the existing FakeLokiClient class in tests/observability/test_services.py

class FakeLokiClient:
    def __init__(
        self,
        result: LokiQueryResult | None = None,
        raises: Exception | None = None,
        tail_entries: list[LokiLogEntry] | None = None,
        tail_raises: Exception | None = None,
    ) -> None:
        self._result = result or LokiQueryResult(entries=[])
        self._raises = raises
        self._tail_entries = tail_entries or []
        self._tail_raises = tail_raises
        self.calls: list[dict] = []
        self.tail_calls: list[dict] = []

    async def query_range(self, **kwargs) -> LokiQueryResult:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._result

    async def tail(self, **kwargs):
        self.tail_calls.append(kwargs)
        if self._tail_raises is not None:
            raise self._tail_raises
        for entry in self._tail_entries:
            yield entry
```

```python
# append to backend/tests/observability/test_services.py

from app.modules.observability.services.stream_log_tail import StreamLogTail


class TestStreamLogTail:
    async def test_raises_not_found_when_unconfigured(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        use_case = StreamLogTail(uow, FakeLokiClient())
        with pytest.raises(LokiConfigNotFound):
            async for _ in use_case.execute(environment_id=uuid4(), query="{}", limit=100):
                pass

    async def test_streams_entries_through(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id, endpoint_url="http://loki:3100", tenant_id="tenant-a",
            auth_type=LokiAuthType.BEARER, credential=FernetCodec.encrypt("tok", key=TEST_FERNET_KEY),
            default_query="", default_range_minutes=60,
        )
        entries = [LokiLogEntry(timestamp="1", line="hello", labels={})]
        client = FakeLokiClient(tail_entries=entries)
        use_case = StreamLogTail(uow, client)

        received = [entry async for entry in use_case.execute(environment_id=env_id, query="{}", limit=100)]

        assert received == entries
        assert client.tail_calls[0]["auth_header"] == "Bearer tok"
        assert client.tail_calls[0]["tenant_id"] == "tenant-a"

    async def test_propagates_client_errors(self) -> None:
        uow = FakeObservabilityUnitOfWork()
        env_id = uuid4()
        await uow.loki_configs.create(
            environment_id=env_id, endpoint_url="http://loki:3100", tenant_id=None,
            auth_type=LokiAuthType.NONE, credential=None, default_query="", default_range_minutes=60,
        )
        client = FakeLokiClient(tail_raises=LokiApiUnavailable())
        use_case = StreamLogTail(uow, client)

        with pytest.raises(LokiApiUnavailable):
            async for _ in use_case.execute(environment_id=env_id, query="{}", limit=100):
                pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/observability/test_services.py -k StreamLogTail -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/modules/observability/services/stream_log_tail.py
from collections.abc import AsyncIterator
from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.integrations.loki.client import LokiClient
from app.integrations.loki.schemas import LokiLogEntry
from app.modules.observability.exceptions import LokiConfigNotFound
from app.modules.observability.services._auth import resolve_loki_auth_header
from app.modules.observability.uow import AbstractObservabilityUnitOfWork


class StreamLogTail(AbstractUseCase):
    def __init__(self, uow: AbstractObservabilityUnitOfWork, client: LokiClient) -> None:
        self._uow = uow
        self._client = client

    @use_case
    async def execute(self, *, environment_id: UUID, query: str, limit: int) -> AsyncIterator[LokiLogEntry]:
        config = await self._uow.loki_configs.get_by_environment_id(environment_id)
        if config is None:
            raise LokiConfigNotFound()

        ciphertext = await self._uow.loki_configs.get_credential_ciphertext(environment_id)
        auth_header = resolve_loki_auth_header(config, ciphertext)

        async for entry in self._client.tail(
            endpoint_url=config.endpoint_url,
            query=query,
            tenant_id=config.tenant_id,
            auth_header=auth_header,
            limit=limit,
        ):
            yield entry
```

Add to `backend/app/modules/observability/dependencies.py`:
```python
async def get_stream_log_tail(
    uow: AbstractObservabilityUnitOfWork = Depends(get_uow),
    client: LokiClient = Depends(get_loki_client),
) -> StreamLogTail:
    return StreamLogTail(uow, client)
```
(with the corresponding `from app.modules.observability.services.stream_log_tail import StreamLogTail` import added alongside the existing service imports.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/observability/ -v`
Expected: PASS — full observability test suite, including all Phase 6 tests unmodified.

- [ ] **Step 5: Commit**

```bash
git add app/modules/observability/services/stream_log_tail.py app/modules/observability/dependencies.py tests/observability/test_services.py
git commit -m "feat(observability): add StreamLogTail use case"
```

---

## Task 4: SSE router endpoint

**Files:**
- Modify: `backend/app/modules/observability/router.py`
- Test: `backend/tests/observability/test_router.py` (append)

**Interfaces:**
- Consumes: `StreamLogTail`/`get_stream_log_tail` (Task 3), `EventSourceResponse` (`sse_starlette.sse`), `ApiResponse`/`ErrorPayload` (`app.core.models`).
- Produces: `GET /environments/{environment_id}/loki-config/tail`.

- [ ] **Step 1: Write the failing tests**

SSE endpoints need a streaming-capable test client. Read `backend/tests/conftest.py`'s `client` fixture first to confirm whether it's built on `httpx.AsyncClient` (it is, per Phase 6's research) — `httpx.AsyncClient` supports streaming responses via `client.stream("GET", ...)`. Mirror the existing router-test dependency-override pattern (`app.dependency_overrides[...]  = lambda: fake`), but override `get_loki_client` (from `app.integrations.loki.dependencies`) with a fake whose `tail` is an async generator, exactly like `test_audit_logs_router.py` did for `get_cloudflare_client` in Phase 6.

```python
# append to backend/tests/observability/test_router.py

import json

from app.integrations.loki.dependencies import get_loki_client
from app.main import app


class FakeTailLokiClient:
    def __init__(self, entries: list | None = None) -> None:
        self._entries = entries or []

    async def query_range(self, **kwargs):
        raise NotImplementedError

    async def tail(self, **kwargs):
        for entry in self._entries:
            yield entry


class TestStreamLogTail:
    async def test_requires_environment_read_permission(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(client, engine, permissions=[], email="notail@x.com")

        response = await client.get(f"/api/v1/environments/{environment_id}/loki-config/tail?query=%7B%7D")
        assert response.status_code == 403

    async def test_404s_when_unconfigured(self, client: AsyncClient, engine: AsyncEngine) -> None:
        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(client, engine, permissions=[("environment", "read")], email="tailreader@x.com")

        response = await client.get(f"/api/v1/environments/{environment_id}/loki-config/tail?query=%7B%7D")
        assert response.status_code == 404

    async def test_streams_entries_as_sse_events(self, client: AsyncClient, engine: AsyncEngine) -> None:
        from app.integrations.loki.schemas import LokiLogEntry

        environment_id = await _make_environment(client, engine)
        await _login_with_permissions(
            client, engine, permissions=[("environment", "update"), ("environment", "read")], email="tailadmin@x.com"
        )
        await client.post(
            f"/api/v1/environments/{environment_id}/loki-config",
            json={
                "endpointUrl": "http://loki:3100", "tenantId": None, "authType": "none",
                "credential": None, "defaultQuery": "", "defaultRangeMinutes": 60,
            },
        )

        fake_client = FakeTailLokiClient(entries=[LokiLogEntry(timestamp="1", line="hello", labels={})])
        app.dependency_overrides[get_loki_client] = lambda: fake_client

        try:
            async with client.stream(
                "GET", f"/api/v1/environments/{environment_id}/loki-config/tail?query=%7B%7D"
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                assert response.headers.get("x-accel-buffering") == "no"
                body_lines = []
                async for line in response.aiter_lines():
                    body_lines.append(line)
                    if len(body_lines) > 5:
                        break
        finally:
            del app.dependency_overrides[get_loki_client]

        data_lines = [line for line in body_lines if line.startswith("data:")]
        assert len(data_lines) >= 1
        payload = json.loads(data_lines[0][len("data:") :].strip())
        assert payload["success"] is True
        assert payload["data"]["line"] == "hello"
```

The exact `get_loki_client` import path must be re-verified against `app/integrations/loki/dependencies.py`'s real content (Task 1 of the Phase 6 plan already created this file — `from app.integrations.loki.dependencies import get_loki_client`) before finalizing this test. `client.stream(...)`'s exact async-context-manager usage must be verified against the installed `httpx` version's real API during implementation — the shape above is httpx's documented streaming pattern, not independently re-confirmed against this repo's exact pinned version.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/observability/test_router.py -k StreamLogTail -v`
Expected: FAIL (404 route not found / `AttributeError`)

- [ ] **Step 3: Write the implementation**

```python
# add to backend/app/modules/observability/router.py

import json
from collections.abc import AsyncIterator

from sse_starlette.sse import EventSourceResponse

from app.core.models import ErrorPayload
from app.modules.observability.dependencies import get_stream_log_tail
from app.modules.observability.services.stream_log_tail import StreamLogTail


@router.get("/environments/{environment_id}/loki-config/tail")
async def stream_log_tail(
    environment_id: UUID,
    query: str,
    limit: int = 100,
    use_case: StreamLogTail = Depends(get_stream_log_tail),
    _user: UserRead = Depends(require_permission(RbacResources.ENVIRONMENT, RbacActions.READ)),
) -> EventSourceResponse:
    """SSE bridge to Loki's WebSocket /tail. Fails fast (normal REST error
    response) if unconfigured — LokiConfigNotFound is raised before any
    event is yielded, so FastAPI's exception handlers still apply normally
    (EventSourceResponse hasn't taken over the response yet at that point).
    Any error after streaming starts is turned into one final
    success:false event instead (Decision #5) — by then the HTTP status is
    already committed and can't be changed."""

    async def event_stream() -> AsyncIterator[dict]:
        try:
            async for entry in use_case.execute(environment_id=environment_id, query=query, limit=limit):
                payload = ApiResponse(success=True, data=entry)
                yield {"event": "message", "data": payload.model_dump_json(by_alias=True)}
        except Exception as exc:  # noqa: BLE001 -- mid-stream errors must become a final SSE event, not propagate
            error = ErrorPayload(code=getattr(exc, "code", "loki_unavailable"), message=str(exc))
            payload = ApiResponse(success=False, error=error)
            yield {"event": "message", "data": payload.model_dump_json(by_alias=True)}

    # LokiConfigNotFound (raised on the first `execute()` step before any
    # yield) propagates out of this generator's first `__anext__` call,
    # which EventSourceResponse surfaces as a normal exception BEFORE
    # streaming starts — reaching FastAPI's own exception handlers as a
    # standard REST error response, not an SSE event. Confirm this exact
    # behavior against the real EventSourceResponse implementation during
    # implementation; if it does not propagate this way in practice, wrap
    # the not-found check as an explicit pre-flight call before entering
    # event_stream() instead, so the 404 is guaranteed to be a normal
    # response rather than swallowed into the try/except above.
    return EventSourceResponse(event_stream(), headers={"X-Accel-Buffering": "no"})
```

The comment block above marks a genuine open question the plan cannot resolve without running the real library: does `EventSourceResponse` call the generator lazily (first `__anext__` happens after the response has already started streaming, i.e. after the 200 status is sent) or does it eagerly pull the first item before committing the response? If eager, `LokiConfigNotFound` raised on the first line of `execute()` surfaces as a normal 404 exactly as Decision #5 wants. If lazy, the 404 would incorrectly appear as a mid-stream SSE event instead of a real HTTP 404. **Verify this directly during Step 4 (Task 4 test `test_404s_when_unconfigured` already asserts `status_code == 404`, not an SSE event body — if that test fails on the status code, this is the reason, and the fix is an explicit pre-flight `await use_case._uow.loki_configs.get_by_environment_id(environment_id)` check in the router handler itself, before constructing `EventSourceResponse` at all, so the 404 is raised and handled the normal way before any streaming machinery is invoked.**

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/observability/test_router.py -v`
Expected: PASS. If `test_404s_when_unconfigured` fails on status code (200 with an error-shaped SSE body instead of a real 404), apply the pre-flight-check fix described in Step 3's note, then re-run.

- [ ] **Step 5: Commit**

```bash
git add app/modules/observability/router.py tests/observability/test_router.py
git commit -m "feat(observability): add SSE live-tail endpoint"
```

---

## Task 5: Full backend verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q`
Expected: all green, including `pyproject.toml`'s new `sse-starlette`/`websockets` entries not triggering any boundary violation (both are leaf integrations, already covered by the existing `integrations-are-leaves` contract's pattern — no `.importlinter` change needed since no new `app.integrations.*` package was created, only a new method on the existing `app.integrations.loki`).

- [ ] **Step 2: Fix any failures, re-run until green**

- [ ] **Step 3: Commit if any fixes were needed**

```bash
git add -A
git commit -m "fix(observability): resolve live-tail verification findings"
```

---

## Task 6: Frontend — `use-log-tail` hook + `shared/constants/api.ts`

**Files:**
- Create: `frontend/src/modules/log-viewer/hooks/use-log-tail.ts`
- Modify: `frontend/src/shared/constants/api.ts`

**Interfaces:**
- Consumes: `LogEntry`, `logEntrySchema` (`../model/schema`, existing from Phase 6), `API_CONFIG`.
- Produces: `useLogTail(environmentId: string, query: string) -> { entries: LogEntry[], isLive: boolean, start: () => void, stop: () => void, error: string | null }`.

- [ ] **Step 1: Add the API endpoint constant**

```typescript
// add to frontend/src/shared/constants/api.ts, inside the existing OBSERVABILITY block
OBSERVABILITY: {
  LOKI_CONFIG: (environmentId: string) => `/environments/${environmentId}/loki-config`,
  LOKI_QUERY: (environmentId: string) => `/environments/${environmentId}/loki-config/query`,
  LOKI_TAIL: (environmentId: string) => `/environments/${environmentId}/loki-config/tail`,
},
```

- [ ] **Step 2: Write the hook**

No dedicated unit test — `EventSource` has no jsdom/vitest-environment implementation in this repo (confirmed: no `EventSource` polyfill or mock exists anywhere in `package.json`/test setup), matching the established precedent that `modules/cloudflare-dns/hooks/*` and Phase 6's own `use-loki-config.ts`/`use-log-query.ts` have no dedicated hook-level tests either — this hook's correctness is exercised by the Task 7 manual smoke test instead, same as every other real-network hook in this module.

```typescript
// frontend/src/modules/log-viewer/hooks/use-log-tail.ts
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_CONFIG } from "@/shared/constants/api";
import { logEntrySchema, type LogEntry } from "../model/schema";

const MAX_BUFFERED_ENTRIES = 500;

interface ApiEnvelope {
  success: boolean;
  data?: unknown;
  error?: { code: string; message: string };
}

export function useLogTail(environmentId: string, query: string) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [isLive, setIsLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const stop = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
    setIsLive(false);
  }, []);

  const start = useCallback(() => {
    setError(null);
    setEntries([]);
    const url = new URL(
      `${API_CONFIG.API_V1_URL}${API_CONFIG.ENDPOINTS.OBSERVABILITY.LOKI_TAIL(environmentId)}`,
      window.location.origin,
    );
    url.searchParams.set("query", query);
    const source = new EventSource(url.toString(), { withCredentials: true });

    source.onmessage = (event) => {
      const envelope = JSON.parse(event.data) as ApiEnvelope;
      if (!envelope.success) {
        setError(envelope.error?.message ?? "Live tail failed");
        stop();
        return;
      }
      const entry = logEntrySchema.parse(envelope.data);
      setEntries((current) => [...current, entry].slice(-MAX_BUFFERED_ENTRIES));
    };

    source.onerror = () => {
      // EventSource auto-reconnects on a dropped connection by design —
      // only surface an error state, never stop() here, or a transient
      // network blip would silently end a session the user expects to
      // keep running until they explicitly pause it.
      setError("Connection interrupted — retrying...");
    };

    sourceRef.current = source;
    setIsLive(true);
  }, [environmentId, query, stop]);

  useEffect(() => stop, [stop]);

  return { entries, isLive, start, stop, error };
}
```

`API_CONFIG.API_V1_URL`'s exact export name must be verified against `shared/constants/api.ts`'s real current shape (confirmed present from Phase 6's own reading of this file: `API_V1_URL: RAW_API_URL ? ... : API_V1_PREFIX`) before finalizing — the URL-construction approach above (`new URL(path, window.location.origin)`) is one valid way to get an absolute URL for `EventSource` (which, unlike `fetch`/`axios`, needs a real URL object or string, not a bare relative path when constructed this way); confirm during implementation whether `apiFetch`'s underlying axios instance already has a `baseURL` configured that could be reused more simply — if so, prefer reading that same base rather than reconstructing it here.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/shared/constants/api.ts frontend/src/modules/log-viewer/hooks/use-log-tail.ts
git commit -m "feat(log-viewer): add useLogTail hook wrapping native EventSource"
```

---

## Task 7: Frontend — Live/Pause toggle in `LokiQueryTab` + i18n

**Files:**
- Modify: `frontend/src/modules/log-viewer/ui/log-viewer-page-content.tsx`
- Modify: `frontend/locales/en/modules/log-viewer.json`
- Modify: `frontend/locales/vi/modules/log-viewer.json`

**Interfaces:**
- Consumes: `useLogTail` (Task 6).

- [ ] **Step 1: Invoke `ui-ux-pro-max` before writing markup**

Mandatory per AGENTS.md Phase 3 rule. Query for a live/streaming-indicator pattern and a toggle-button pair:
```bash
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "live status indicator streaming real-time" --domain ux
python "/Users/hoangdieu/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.13.0/.claude/skills/ui-ux-pro-max/scripts/search.py" "toggle button pressed state accessible" --domain ux
```
Apply results to: a visibly distinct "Live" state (not color-alone, per this repo's own established `TunnelStatus` badge precedent from Phase 5 — icon + text), `aria-pressed` on the toggle button, and disabling the Start/End range inputs while live (tailing has no end time) without their disabled state being invisible/unexplained to a screen reader user (add `aria-describedby` pointing at a short hint, mirroring the `record-type-hint`/`isEditing` disabled-field pattern already used in `dns-record-form-dialog.tsx`).

- [ ] **Step 2: Modify `LokiQueryTab`**

Read the current (Phase 6) `LokiQueryTab` component in full first. Add:
```tsx
import { useLogTail } from "../hooks/use-log-tail";
// ... inside LokiQueryTab, alongside the existing useRunLogQuery():
const tail = useLogTail(environmentId, query);
const displayedEntries = tail.isLive ? tail.entries : runQuery.data;
```
Add a Live/Pause `<Button>` next to the existing "Run query" submit button:
```tsx
<Button
  type="button"
  variant={tail.isLive ? "destructive" : "outline"}
  aria-pressed={tail.isLive}
  onClick={() => (tail.isLive ? tail.stop() : tail.start())}
>
  {tail.isLive ? t("query.pause") : t("query.live")}
</Button>
```
Disable the Start/End `<Input type="datetime-local">` fields and the "Run query" submit button while `tail.isLive` is true (`disabled={tail.isLive}`, plus `aria-describedby="loki-live-hint"` on each, with a `<p id="loki-live-hint" className="sr-only">{t("query.liveHint")}</p>` — visually hidden but announced). Render `tail.error` the same way the existing `errorMessage` state is rendered (reuse the existing `role="alert"` block, do not duplicate the pattern).

Replace `LogResultsTable`'s `entries` prop with `displayedEntries ?? []` in the JSX below the form (was `runQuery.data` alone in Phase 6).

- [ ] **Step 3: i18n**

```json
// add to frontend/locales/en/modules/log-viewer.json's "query" block
"live": "Go Live",
"pause": "Pause",
"liveHint": "Time range is disabled while live tailing — new lines stream in as they arrive."
```
```json
// add to frontend/locales/vi/modules/log-viewer.json's "query" block
"live": "Live",
"pause": "Tạm dừng",
"liveHint": "Khoảng thời gian bị vô hiệu hoá khi đang xem trực tiếp — dòng log mới sẽ tự động xuất hiện."
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build`
Expected: all green, `/admin/environments/[environmentId]/logs` route still registers in the build output.

- [ ] **Step 5: Manual smoke test**

If a real or locally-run Loki instance is reachable, configure it for a test environment, click "Go Live," confirm lines stream without polling, close the tab, and confirm (via the backend's own logs or a temporary debug print in `LokiClient.tail`) that the upstream WebSocket closed rather than being left dangling. This step requires external infrastructure this environment does not have running by default — disclose explicitly if skipped rather than claiming it passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/modules/log-viewer/ui/log-viewer-page-content.tsx frontend/locales
git commit -m "feat(log-viewer): add Live/Pause toggle wired to useLogTail"
```

---

## Task 8: GitNexus + skills review + finish branch

**Files:** none (verification + branch lifecycle only).

- [ ] **Step 1: Re-index and review impact**

```bash
node .gitnexus/run.cjs analyze
```
If `detect_changes`/`check` MCP tools are exposed this session, use them; otherwise `git diff develop..feature/loki-live-tail --stat` and compare against this plan's Architecture Impact section.

- [ ] **Step 2: Full verification, both stacks**

```bash
cd backend && ruff check && ruff format --check && python scripts/check_module_boundaries.py --strict && lint-imports && uv run pytest -q
cd ../frontend && npx tsc --noEmit && npm run lint && npx vitest run && npm run build
```

- [ ] **Step 3: `reviewing-code-against-skills` checklist**

Fix loop: max 2 rounds for architectural findings, unlimited for mechanical/lint findings.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch. Present the standard 3-option menu (base branch `develop`). On "Merge back to develop locally": merge `--no-ff`, re-run both verification commands from Step 2 against the merged result, delete the branch only after both pass.
