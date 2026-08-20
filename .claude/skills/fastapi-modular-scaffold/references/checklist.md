# Pre-production checklist

Run this before the first real traffic, and again after any structural change.

## Structure

- [ ] `lint-imports` passes in CI, not just locally
- [ ] Every table has exactly one owning module
- [ ] No service imports `HTTPException`
- [ ] No cache key built outside `integrations/cache/keys.py`
- [ ] No `os.getenv` outside a `config.py`
- [ ] No `utils.py` or `helpers.py` at the root
- [ ] `app/core/exceptions.py` names no domain entity
- [ ] `app/constants.py` holds no business limit
- [ ] No module's `constants.py` imports another module's `constants.py`
- [ ] No repository calls `commit()`
- [ ] No file over ~500-600 lines — split into a subpackage (`router/`, `repository/`) instead of leaving it flat
- [ ] `ruff check` reports no `C901` (function complexity over 15)
- [ ] `ruff check` reports no `PLC0415` (import inside a function body) — a local import that exists to dodge a circular import means the real fix is moving code across a layer boundary, not keeping the local import
- [ ] Every domain module has a `tests/<module>/` folder — no module without one, no test colocated inside `app/`, no flat `tests/test_everything.py`
- [ ] `.env.prod` exists, is gitignored, and every secret in it differs from `.env` — check by diffing key-by-key, not just confirming the file exists
- [ ] `.env.example` documents every `Settings` field with its own Python-side default — run `uv run python scripts/check_env_example.py` after adding or renaming a `Settings` field; it fails loudly if any field's fully-prefixed env var name is missing from `.env.example`
- [ ] If the `queue` integration is present, `app/worker.py` runs as its own container/process — never imported into or started from `app/main.py`
- [ ] No `if user.role == "..."` (or similar role-string comparison) anywhere in a router or service — permission checks go through `require_permission(resource, action)`, never a hardcoded role name (see `references/rbac.md`)
- [ ] Every permission check is scoped to an `organization_id` — a check with no organization scope is the global-role mistake `references/rbac.md` exists to prevent
- [ ] `ruff check` reports no `PGH003`/`PGH004` (blanket `# type: ignore`/`# noqa`) — every suppression names a specific code and a reason after `--`
- [ ] Every `repository.py`/`uow.py` defines an `Abstract{X}Repository`/`Abstract{X}UnitOfWork` extending the root's `AbstractRepository`/`AbstractUnitOfWork`, and every `services/*.py` class extends `AbstractUseCase` — see `references/layer-examples.md`
- [ ] A service's constructor is typed against the `Abstract*` contract, never the concrete SQLAlchemy class — only `dependencies.py` (the composition root) names the concrete class
- [ ] No bare `NAME = value` or bare `def helper(...)` above a class in `constants.py`, `rules.py`, or a file inside `utils/` — a constant is a class attribute, a helper is a `@staticmethod` (rule #16). Does not apply to `router.py`/`dependencies.py`/`lifespan.py`, which stay plain FastAPI-callable functions
- [ ] `utils.py` is a package (`utils/__init__.py` + one file per concern), not a single growing file
- [ ] `tests/<module>/test_services.py` exists alongside `test_rules.py`/`test_router.py` — a `Fake{X}Repository`/`Fake{X}UnitOfWork` unit-tests the use case with no database

## Database

- [ ] Alembic migration for every model change; `alembic upgrade head` runs on a clean DB
- [ ] Downgrade tested at least once — the first time you need it will be during an incident
- [ ] Indexes on every foreign key and every column used in a `WHERE`
- [ ] Pool size reasoned about, not defaulted: `pool_size * replicas < max_connections`
- [ ] PgBouncer in transaction mode if replica count is high
- [ ] Statement timeout set — one runaway query should not take the pool with it

## Cache

- [ ] Invalidation happens after commit, and rollback drops it
- [ ] `ValidationError` on read is treated as a miss
- [ ] Redis outage degrades to slow, not broken — test by killing Redis
- [ ] TTL set on every key including versions
- [ ] `maxmemory-policy` set (`allkeys-lru` for pure cache)

## Messaging

- [ ] Every queue declared with a dead-letter exchange
- [ ] Consumers idempotent, verified by replaying a message — via `integrations/queue/idempotency.py`'s `idempotent(store)` or a naturally idempotent handler, not assumed
- [ ] Retry capped with backoff; failures land somewhere a human sees
- [ ] Prefetch bounded
- [ ] SIGTERM drains in-flight work

## API

- [ ] No ORM model returned from an endpoint
- [ ] Domain errors mapped centrally with stable codes
- [ ] Pagination on every list endpoint, with a maximum page size
- [ ] Request id propagated through logs and into published events
- [ ] `/health` (liveness) separate from `/ready` (dependencies reachable)
- [ ] Every endpoint returns `ApiResponse[...]` — no bare schema, no hand-built error dict (see `references/api-contract.md`)
- [ ] Every schema inherits `CustomModel`/`FrozenModel` (or `Page`) so the wire format is camelCase, not `PaginationParams`-style snake_case leaking through
- [ ] No route ever puts `ErrorPayload.message` in front of a user — that's the frontend i18n system's job, keyed on `error.code`
- [ ] `main.py` handles `RequestValidationError`, not just `AppError` and `Exception` — otherwise a schema `field_validator` failure returns FastAPI's default `{"detail": [...]}` instead of the envelope
- [ ] A schema's `field_validator`/`field_serializer` for a field calls into that module's `rules.py`/`utils/` rather than reimplementing the check inline — one implementation of the rule, invoked from both the wire boundary and the use case
- [ ] `app/core/database.py`'s `get_session` commits on success and rolls back on failure — required for any `--minimal` module, since its repository only ever calls `flush()`

## Operations

- [ ] Structured JSON logs; no secrets, tokens or emails in them
- [ ] `request_id` and `correlation_id` are both bound (not conflated) — see `references/logging.md`
- [ ] A published message carries `correlation_id`; the consumer re-binds it before running the handler
- [ ] `SENSITIVE_KEYS` in `logging_config.py` covers every field this specific project logs that shouldn't be, not just the generated default set
- [ ] Metrics for latency, error rate, cache hit rate, queue depth
- [ ] Alert on queue depth growth and DLQ non-empty
- [ ] Rate limiting at the edge
- [ ] Graceful shutdown verified under a rolling deploy

## Load behaviour

- [ ] Behaviour under a cold cache is known, not assumed
- [ ] Load shedding or a request timeout exists — degrading beats collapsing
- [ ] Slow dependencies are bounded by timeouts everywhere, including Redis and the broker
