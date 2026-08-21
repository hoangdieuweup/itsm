# Logging: structured, correlated, redacted

Every generated project ships this by default — nothing here is opt-in the way `cache`/`queue`/`storage` are. The three pieces: `structlog` configured with a stdlib bridge so a plain `logging.getLogger(__name__)` call anywhere gets the same JSON shape, `RequestIdMiddleware` binding request/correlation ids to every log line in a request, and a redaction processor stripping sensitive fields before anything is written.

## Goals

- Every log line belonging to one request, one message, or one flow that spans services carries the same correlating id.
- Logs are structured (JSON in stg/prod, a readable console renderer in dev) — never a formatted string that has to be re-parsed to query.
- Context (`request_id`, `correlation_id`, `trace_id`/`span_id`, and anything a route binds — `user_id`, `organization_id`) attaches automatically once bound; nothing downstream has to thread it through function signatures by hand.
- Compatible with OpenTelemetry and any log aggregator that ingests JSON (Loki, ELK, CloudWatch, Datadog) without a project-specific parser.

## The id types

| Id | Answers | Field | Header | Bound where |
|---|---|---|---|---|
| `request_id` | Which request, in this service, produced this log line | `request_id` | `X-Request-ID` | `RequestIdMiddleware` (`app/core/middleware.py`) |
| `correlation_id` | Which end-to-end flow this belongs to, across every service and every queue hop it touches | `correlation_id` | `X-Correlation-ID` | `RequestIdMiddleware`; `Broker.publish`/`consume` (`integrations/queue/client.py`) |
| `trace_id` / `span_id` | Where this sits in an OpenTelemetry trace | `trace_id`, `span_id` | W3C `traceparent` | `logging_config.py`'s `_add_trace_context` processor, only when the `tracing` integration is selected |
| A business id | `user_id`, `organization_id`, `order_id`... | whatever name fits | none | bound ad hoc, e.g. inside `get_current_user` |

`request_id` is per hop: fresh every time a request enters this service, unless the caller is retrying the exact same request and passes `X-Request-ID` again. `correlation_id` is the root id for the whole flow: read from `X-Correlation-ID` if a caller propagated one, otherwise this hop originates the flow and `correlation_id` starts out equal to `request_id`. Conflating the two loses the ability to tell "retried this exact call" from "same business flow, different call."

## Where this lives

```python
# app/middleware.py
class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        correlation_id = request.headers.get("x-correlation-id") or request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response
```

`structlog.contextvars.clear_contextvars()` at the top matters as much as the bind — without it, context bound by a previous request handled on the same worker (in a threadpool-backed sync path, or a bug elsewhere) could leak into this one.

`app/core/logging_config.py` merges that context into every line via `structlog.contextvars.merge_contextvars` in the shared processor chain, whether the call site used `structlog.get_logger(__name__)` or plain stdlib `logging.getLogger(__name__)` — the `ProcessorFormatter` bridge is what makes the stdlib call get the same treatment, so nothing in the codebase has to choose between the two consistently.

## Redaction

```python
SENSITIVE_KEYS = {"password", "token", "authorization", "secret", "api_key", "credit_card"}

def _redact_sensitive(logger, method_name, event_dict):
    for key in event_dict:
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
    return event_dict
```

Already in the shared processor chain, so it runs for every log line regardless of call site. Add a key to `SENSITIVE_KEYS` rather than remembering to mask it at each call site — the whole point is that a call site shouldn't have to know.

## Propagation across boundaries

### Queue (real, generated code)

`Broker.publish` (`integrations/queue/client.py`) reads `correlation_id` off the current context and carries it on AMQP's own `correlation_id` basic property — not a custom header, the field the protocol already has for exactly this — falling back to the event's own id when publishing outside a request (a worker, a seed script):

```python
correlation_id = structlog.contextvars.get_contextvars().get("correlation_id", event.event_id)
message = aio_pika.Message(
    body=event.model_dump_json().encode(),
    ...,
    correlation_id=correlation_id,
)
```

`Broker.consume` reads it back off the message and re-binds it before calling the handler, the same way the middleware does for an HTTP request:

```python
structlog.contextvars.clear_contextvars()
structlog.contextvars.bind_contextvars(
    correlation_id=message.correlation_id or message.message_id,
    message_id=message.message_id,
)
await handler(message.body)
```

The handler itself needs no changes — a plain `logging.getLogger(__name__).info(...)` call inside it already carries `correlation_id` once this runs. A log line in the API that published the event and a log line in the worker that consumed it now share one id, queryable as one flow even though they're two processes.

### Outbound HTTP to another internal service

Not generated automatically — whether a project calls another internal service is project-specific, the same way `queue`/`storage` are opt-in. The pattern, when needed:

```python
import httpx
import structlog

async def call_internal_service(url: str, **kwargs) -> httpx.Response:
    """Propagate the current flow's correlation id to a downstream service call."""
    context = structlog.contextvars.get_contextvars()
    headers = kwargs.pop("headers", {})
    headers["X-Correlation-ID"] = context.get("correlation_id", "")
    async with httpx.AsyncClient() as client:
        return await client.request("GET", url, headers=headers, **kwargs)
```

If the `tracing` integration is selected, `FastAPIInstrumentor` and OpenTelemetry's `httpx` instrumentation (added separately, not part of this scaffold) handle W3C `traceparent` propagation automatically — `correlation_id` and `traceparent` are complementary, not a choice between them: `traceparent` is what OpenTelemetry needs to stitch spans together, `correlation_id` is what a human greps a log aggregator for without needing a trace UI open.

## Business context

Bind a business id the same way, wherever it becomes known — typically inside a dependency, not the route body, so every handler that depends on it gets it automatically:

```python
async def get_current_user(token: str = Depends(oauth2_scheme)) -> IdentityRead:
    user = await _decode_and_load(token)
    structlog.contextvars.bind_contextvars(user_id=user.id)
    return user
```

Bind, don't pass through function signatures purely so a deeply nested log call can reach it — that's exactly the coupling `contextvars` exists to avoid.

## Log levels

- `DEBUG` — development detail, off by default in stg/prod (`Environment.is_debug` gates it — see `app/constants.py`)
- `INFO` — a business event worth a permanent record (`order_created`, `payment_captured`)
- `WARNING` — abnormal but handled (cache miss degrading to a DB read, a retry)
- `ERROR` — something failed and needs a human eventually
- `CRITICAL` — the process itself is in danger (reserve for genuinely system-level failure, not a single request's error — that's `ERROR`)

## Checklist

- [ ] Every service in the system uses the same field names: `request_id`, `correlation_id`, `trace_id`, `span_id` — a renamed field on one service breaks cross-service search
- [ ] `RequestIdMiddleware` is registered before any other middleware that logs, so its context is bound first
- [ ] JSON rendering in stg/prod, console rendering in dev (`settings.ENV.is_debug` already gates this in `logging_config.py`)
- [ ] A message published to the queue carries `correlation_id`; the consumer binds it back before running the handler
- [ ] A call to another internal service propagates `X-Correlation-ID`, and `traceparent` too if `tracing` is enabled
- [ ] `SENSITIVE_KEYS` covers every field this project actually logs that shouldn't be — audit it per project, the default set is a starting point, not exhaustive
- [ ] The log aggregator in use can filter/search by `correlation_id` across every service that emits it — verify this against the real aggregator (Loki, ELK, CloudWatch...), not assumed from the field being present
