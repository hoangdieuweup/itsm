# API contract: camelCase, the response envelope, and i18n

The wire format is a contract with whatever consumes it — usually a frontend on a different stack with different naming conventions. This file is the single source of truth for that contract; `app/core/models.py` is where it's enforced in code.

## camelCase on the wire, snake_case in Python

`CustomModel`/`FrozenModel` (`app/core/models.py`) set `alias_generator=to_camel` plus `populate_by_name=True`. Every schema that inherits from them — which is all of them, including `Page` — gets this for free:

```python
class IdentityRead(FrozenModel):
    created_at: datetime  # Python code: snake_case, as normal
```
```json
{"createdAt": "2026-08-19T12:00:00+0000"}
```

Nothing else is needed per-field. A schema that does **not** inherit `CustomModel`/`FrozenModel` won't get this — that should only happen for something that's genuinely not a wire model (`PaginationParams` reads query params, not a JSON body, so it stays plain `BaseModel`).

## The response envelope

Every endpoint returns the same shape, success or failure, REST or SSE:

```json
{ "success": true,  "data": { "id": 1, "name": "Example" }, "error": null }
{ "success": false, "data": null, "error": { "code": "identity_not_found", "message": "Resource not found", "context": {} } }
```

`ApiResponse[T]` and `ErrorPayload` (`app/core/models.py`) are the two pieces. A router returns `ApiResponse(success=True, data=result)`; the three exception handlers in `main.py` build the failure half automatically — a route never constructs an error envelope by hand:

- `handle_app_error` for `AppError` subclasses (a domain error a service raised)
- `handle_validation_error` for `RequestValidationError` — this is what a schema's `field_validator` failure turns into (see `references/layer-examples.md#schemaspy--validation-and-serialization-live-on-the-schema`); without this handler, a bad request body would return FastAPI's own default `{"detail": [...]}` shape instead of the envelope, since `RequestValidationError` isn't an `AppError`
- `handle_unexpected_error` for everything else

A paginated list is `ApiResponse[Page[IdentityRead]]` — the envelope wraps `Page`, `Page` wraps the items. Don't flatten this; a client that already has one shared "unwrap the envelope" helper should not need a second one for lists.

### SSE

The same envelope goes inside every event's `data:` field, so a client can reuse the exact same unwrap logic regardless of transport:

```python
from sse_starlette.sse import EventSourceResponse

async def event_stream():
    async for item in some_source():
        payload = ApiResponse(success=True, data=item)
        yield {"event": "message", "data": payload.model_dump_json(by_alias=True)}

@router.get("/stream")
async def stream() -> EventSourceResponse:
    return EventSourceResponse(event_stream())
```

On failure mid-stream, yield one final event carrying `ApiResponse(success=False, error=...)` rather than closing the connection silently — a client with no error event to read has no way to distinguish "finished" from "broke."

## Error codes are the i18n key, not the message

`ErrorPayload.code` (`AppError.code` under the hood — see `placement.md` for where a module's error codes live) is a stable, non-localized string like `identity_not_found`. `ErrorPayload.message` is an English default, meant for logs, for API consumers with no i18n layer, and as a fallback when a translation is missing — **never** render `message` directly to an end user once the frontend has i18n.

The frontend's job (see `nextjs-modular-architecture`'s workflow — it checks for i18n before writing any user-facing string): look up `error.code` in its translation files, falling back to `error.message` only if no i18n system exists in that project at all. This keeps the backend ignorant of locale entirely — it only ever emits one stable key per failure mode, which is what makes the key stable enough to translate.

## Verify before handing over

Add to the existing check:
```bash
uv run python -c "
from app.main import app
from fastapi.testclient import TestClient
r = TestClient(app).get('/health')
assert 'success' not in r.json(), 'health is a liveness probe, not enveloped — this is intentional'
"
```
`/health` is deliberately the one endpoint outside the envelope — it exists for infrastructure (load balancer probes), not API consumers, and should stay a trivial `{"status": "ok"}` that never changes shape.
