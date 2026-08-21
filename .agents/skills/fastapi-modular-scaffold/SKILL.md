---
name: fastapi-modular-scaffold
description: Scaffold and extend production-grade modular FastAPI projects with PostgreSQL, Redis, RabbitMQ and object storage, following the Netflix Dispatch convention where every module owns its own constants, enums, config, exceptions and helpers, and every integration is a module rather than a flat utility folder. Use this skill whenever the user asks to start a new backend or API project, set up or review a FastAPI project structure, add a module or feature to an existing FastAPI codebase, decide where constants, enums, exceptions or utils should live, wire up Redis caching or cache invalidation, add a queue or worker, or asks how to organize a large Python backend — even if they don't say "modular monolith" or "scaffold" explicitly.
---

# FastAPI Modular Scaffold

Build backends that survive growth. The organizing idea, taken from Netflix Dispatch and the widely used `zhanymkanov/fastapi-best-practices` convention, is that **a module owns everything it needs**: its tables, its enums, its error codes, its settings, its helpers. The application root holds mechanism only — base classes and connections — and no business concept at all.

This inverts the instinct to create `shared/utils.py` and `shared/constants.py`. Those files start small, accumulate everything, and end up imported by every module while importing from several — a new version of the mess the structure was meant to prevent. The one sanctioned exception is `modules/common/` — a real module, not a dumping ground, that a concept only enters once it clears the promotion bar in `references/placement.md#when-duplication-is-correct` (needed by three or more modules, stable, and one where divergence would be a bug). See rule #17.

## When to do what

| Situation | Action |
|---|---|
| New project | Run `scripts/scaffold.py`, then read `references/architecture.md` |
| Add a domain module | `scripts/scaffold.py --add-module <name>` |
| Add cache, queue, storage or tracing | `scripts/scaffold.py --add-integration <name>` |
| "Where does this constant/enum/exception go, or does it belong in `modules/common`?" | Read `references/placement.md` |
| Circular-import error, or unsure which file in a module is allowed to import which | Read `references/architecture.md#intra-module-import-order` |
| Full worked example of every layer, with `Abstract*` classes and validation on schemas | Read `references/layer-examples.md` |
| Wire caching, fix stale data | Read `references/caching.md` |
| Add queue, outbox, consumers | Read `references/messaging.md` |
| Wire a new endpoint, decide the response shape, error codes, SSE | Read `references/api-contract.md` |
| Deploy, set up env files, add a seed script | Read `references/deployment.md` |
| Add permissions, roles, org/department-scoped access | Read `references/rbac.md` |
| Correlate logs across a request, a queue hop, or a downstream service call | Read `references/logging.md` |
| Before shipping | Walk `references/checklist.md` |

Ask what infrastructure the project actually needs before generating. A queue added to a project with no async work is weight the team carries forever.

**Works alongside:** if this system also has a Next.js/React frontend, that half is governed by the `nextjs-modular-architecture` skill, not this one — same shape of rules (modular, layered, one-way dependencies, ~500-600 line file budget), different stack. After changing code on either side, run `reviewing-code-against-skills` before calling the work done — it finds whichever of these two skills governs the files that changed and checks against that skill's actual rules rather than generic style.

## Generating

```bash
python scripts/scaffold.py --name shop --output ./shop \
    --modules identity,billing --integrations cache,queue
```

`--integrations` accepts `cache`, `queue`, `storage`, `tracing`. `--minimal` drops the unit of work for small projects. `--add-module` and `--add-integration` extend an existing tree.

Every generated project ships structured logging by default, not just when an integration is added: `structlog` configured with a stdlib bridge (so every `logging.getLogger(__name__)` call already used across the templates emits the same JSON), a `RequestIdMiddleware` that binds `request_id` (this hop) and `correlation_id` (the whole flow) to every log line in a request and echoes both back as `X-Request-ID`/`X-Correlation-ID`, and redaction of `password`/`token`/`authorization`/`secret`/`api_key`/`credit_card` fields. `correlation_id` propagates through the `queue` integration too — see `references/logging.md`. Add the `tracing` integration to also merge `trace_id`/`span_id` from OpenTelemetry into every log line.

## The structure

```
app/
├── main.py              routers, error handler
├── lifespan.py          the ONLY place pools are created
├── config.py            global settings ONLY (db, env, cors)
├── constants.py         global enums ONLY (Environment)
├── worker.py            queue consumer process — only when `queue` is selected, its own container
│
├── core/                shared mechanism — no business concept lives here
│   ├── database.py      Base, session, naming conventions
│   ├── models.py        CustomModel / FrozenModel base
│   ├── exceptions.py    AppError base classes — no domain errors
│   ├── pagination.py    Page, PaginationParams
│   ├── events.py        DomainEvent base, EventBus
│   ├── middleware.py    RequestIdMiddleware — binds request_id to every log line
│   ├── logging_config.py structlog + stdlib bridge, JSON in stg/prod, console in dev
│   ├── docs.py          docs_url matrix + the staging HTTP Basic auth guard
│   ├── retry.py         @retry(attempts=..., exceptions=...) — backoff for transient failures
│   └── base/            abstract contracts — rule #15
│       ├── repository.py AbstractRepository[T] — root contract
│       ├── uow.py        AbstractUnitOfWork — root contract
│       ├── use_case.py   AbstractUseCase — root contract
│       └── markers.py    @database/@helper/@rule/@use_case/@facade/@integration — rule #16
│
├── seeds/                idempotent one-off scripts, run via `python -m app.seeds.<name>`
│
├── modules/             domain modules — each owns everything it needs
│   ├── identity/
│   │   ├── constants.py     its enums, its error codes, its limits — grouped into classes, rule #16
│   │   ├── config.py        its settings (IDENTITY__ prefix)
│   │   ├── exceptions.py    UserNotFound, EmailTaken — concrete errors
│   │   ├── schemas.py       Pydantic — field_validator/field_serializer live here, rule #15/#16
│   │   ├── models.py        ORM — only this module queries these tables
│   │   ├── rules.py         pure decisions, no I/O — one class, @rule
│   │   ├── utils/           formatting and normalization, no decisions — one class per concern, @helper
│   │   ├── repository.py    Abstract{X}Repository + the concrete class, @database
│   │   ├── uow.py           Abstract{X}UnitOfWork + the concrete class, @database
│   │   ├── services/        one file = one use case, each extends AbstractUseCase, @use_case
│   │   ├── events.py        events it publishes
│   │   ├── dependencies.py  Depends wiring — the composition root, the one place a concrete class is named
│   │   ├── router.py        HTTP surface
│   │   └── public.py        the ONLY import surface for other modules, @facade
│   ├── billing/ ...     same shape, one folder per domain module
│   └── common/          only once 3+ modules need the same concept — rule #17
│       ├── constants.py     the promoted enum/limit, still grouped into a class, rule #16
│       └── public.py        every domain module imports through here or `common.constants`, never the reverse
│
└── integrations/
    ├── cache/           client.py config.py constants.py exceptions.py keys.py
    ├── queue/           client.py config.py constants.py exceptions.py topology.py
    ├── storage/         client.py config.py constants.py exceptions.py
    └── tracing/         client.py config.py constants.py — OpenTelemetry, no tables, no HTTP

tests/                   OUTSIDE app/, mirrors its module layout — never colocated, never one flat file
├── conftest.py          Postgres container, HTTP client, tables truncated between tests
├── identity/
│   ├── test_rules.py    pure unit tests, no fixtures
│   ├── test_services.py use-case unit tests against a Fake repository/uow — no database
│   └── test_router.py   integration tests via the client fixture, real Postgres
└── billing/ ...         same shape, one folder per domain module

Makefile, docker-compose.yml (dev), docker-compose.prod.yml, scripts/start.sh,
scripts/start-worker.sh (if queue) — see references/deployment.md
```

An integration is a module like any other. It differs from a domain module only in what it lacks: no `models.py` because it owns no tables, no `router.py` because it exposes no HTTP. It still owns its own config, constants and exceptions.

## Placement rules

The recurring question is where a given piece of code belongs. The test is **who owns the concept**, not what shape the code has.

| Code | Goes to |
|---|---|
| `OrderStatus`, `MAX_SEATS`, error codes | `<module>/constants.py` |
| `OrderNotFound`, `SeatLimitReached` | `<module>/exceptions.py` |
| `AppError`, `NotFoundError` base classes | `app/core/exceptions.py` |
| `JWT_SECRET`, `CACHE_TTL` for one module | `<module>/config.py` |
| `DATABASE_URL`, `CORS_ORIGINS` | `app/config.py` |
| `can_cancel_order()` — a decision | `<module>/rules.py`, as a `@rule`-decorated class method |
| `slugify()`, `normalize_email()` — a transform | `<module>/utils/`, as a `@helper`-decorated class method |
| `Page`, `CustomModel`, session factory | `app/core/`, as mechanism |
| `AbstractRepository`, `AbstractUnitOfWork` | `app/core/base/`, as abstract contract |
| `@database`, `@helper`, `@rule` markers | `app/core/base/markers.py` |
| `UserStatus` or another enum/limit 3+ modules need | `modules/common/constants.py` — promotion only, never a first draft |

The line between `rules.py` and `utils/` is worth holding: rules encode business decisions and change when the business changes; utils are formatting and shaping and don't. Keeping them apart means rules stay small and heavily tested while utils stay boring. Both live inside a class per rule #16 — see `references/layer-examples.md`.

`app/core/exceptions.py` naming a domain entity is the earliest visible sign the boundary has leaked. So is any `utils.py` at the root.

## Non-negotiable rules

**1. Modules reach each other only through `public.py`.** Never `models.py`, never `repository.py`. Enforced in CI by `lint-imports` and `scripts/check_module_boundaries.py`, because reviewers get tired and linters don't.

**2. Cross-module imports name the module.**

```python
from app.identity import constants as identity_constants
from app.billing.constants import ErrorCode as BillingErrorCode
```

Reading the call site tells you where the constant came from. A bare relative import does not.

**3. One table has exactly one owning module.** Cross-module reads go through the facade. No SQL JOIN across boundaries; compose in the service. This costs a query and buys the ability to split later.

**4. The root holds mechanism, never a business concept.**

**5. Cache keys are built only in `integrations/cache/keys.py`.** Each module supplies its entity name via its own `constants.py`.

**6. Invalidate after commit, never before.** Bumping first lets a concurrent reader repopulate from the pre-commit state. `mark_stale()` queues; `commit()` flushes on success only.

**7. Cache entities, not join results.** A cached `user+tenant` blob has two invalidation triggers and one will be missed.

**8. Pools live in `lifespan.py`.** A pool created per request is not a pool.

**9. One use case = one class with one `execute()`.** Growth adds files, not lines to a service.

**10. Routers hold no business logic.** They translate HTTP to a use-case call. Domain errors map to status codes centrally in `main.py`.

**11. Env var prefixes mirror the module's folder name, never a vendor name, and always end in a double underscore.** `integrations/cache/` reads `CACHE__*`, not `REDIS_*` and not `CACHE_*` — swapping Redis for another backend shouldn't force every deployment's `.env` to change, and the trailing `__` marks the variable as owned/nested under that module rather than a root-level, common setting. Same rule for every domain module (`IDENTITY__*`) and every integration, regardless of whether the folder name itself already contains an underscore (`integrations/dx_core/` → `DX_CORE__*`) or not (`cache` → `CACHE__*`, `auth` → `AUTH__*`) — one convention, no single-word exception to remember. Only the root, common settings in `app/config.py` (`DATABASE_URL`, `CORS_ORIGINS`, `ENV`, ...) stay unprefixed.

**12. No file over ~500-600 lines, no function over cyclomatic complexity 15.** `ruff`'s `C901` enforces the second one; the first is a judgment call made at review time. Neither is a reason to write a flatter module — split the file into a subpackage instead. See `references/architecture.md#keeping-files-and-functions-small`.

**13. Imports live at the top of the file. No circular imports, ever.** `ruff`'s `PLC0415` rejects a function-body import. The one narrow exception is breaking an actual circular-import crash — and that is a symptom to fix, not a pattern to reach for: it means two files depend on each other and one of them is on the wrong side of a layer boundary. Move the shared piece down a layer (into `constants.py`/`schemas.py`, or up into `public.py`) instead of hiding the cycle behind a local import.

**14. No `# noqa`/`# type: ignore` without both a specific code and a stated reason.** `ruff`'s `PGH004`/`PGH003` reject the blanket form (`# noqa` with no code silences everything on the line, not just the one violation it was meant for). That's necessary but not sufficient — a bare `# noqa: F401` still doesn't say *why*. Write `# noqa: F401 -- registers the model on Base.metadata for autogenerate`, the same `-- reason` convention as ESLint. A suppression comment is a decision that needs to survive the person who wrote it leaving the team; if there's no real reason, the fix is the actual problem, not the comment.

**15. `repository.py`, `uow.py` and every `services/*.py` class extend an `Abstract*` contract owned by `core/base/`.** `app/core/base/repository.py` (`AbstractRepository[T]`), `app/core/base/uow.py` (`AbstractUnitOfWork`) and `app/core/base/use_case.py` (`AbstractUseCase`) — a module's concrete `{X}Repository`/`{X}UnitOfWork`/use-case classes implement these, and every service depends on the abstraction, never the concrete SQLAlchemy class. Enforced by Python itself: an incomplete implementation raises `TypeError` at instantiation, not a lint warning at review time. `dependencies.py` is the one composition root allowed to name the concrete class. This is what makes a `Fake{X}Repository` unit test possible — see `references/layer-examples.md`.

**16. No bare constant, type alias, or bare helper function at module level.** A limit, a cache key, a type alias, a text formatter — every one still lives in the file that owns it (`constants.py`, `utils/`) and still gets imported from there, but nothing sits outside a class *within* that file: `CatalogLimits.MAX_NAME_LENGTH`, not a loose `MAX_NAME_LENGTH = 255`; `AuthCookies.SameSite` (a `Literal["lax", "none", "strict"]`), not a `_SameSite = Literal[...]` at the top of whichever file happens to use it; `CatalogTextUtils.normalize_name(...)`, not a bare `def normalize_name(...)`. Type aliases (`Literal`, `TypeAlias`, `TypeVar`) are constants — they belong in `<module>/constants.py` as a class attribute of the class that owns the concept, not scattered across utility or service files. `utils.py` is a package (`utils/__init__.py` + one file per concern), the same way `services/` is one file per use case. This does not reach `router.py`/`dependencies.py`/`lifespan.py` — a FastAPI dependency provider has to stay a plain function `Depends()` calls directly. `app/core/base/markers.py`'s `@database`/`@helper`/`@rule`/`@use_case`/`@facade`/`@integration` decorator classes tag each **method** with its role — never the whole class, since a class has main operations and auxiliary ones supporting them (a repository's `get_by_id` vs. its private `_load_by_id`) — visible at the method's definition, not only inferable from the file. `app/core/retry.py`'s `@retry` and `integrations/queue/idempotency.py`'s `@idempotent` are a different kind of decorator — they change behavior, not just tag it — and stack under a role marker (`@integration` outermost) rather than living in `markers.py`. See `references/layer-examples.md`.

**17. `modules/common/` is the only sanctioned shared module, and it is one-way.** Every domain module may import it, the same as any other module (through `common.public` or `common.constants`, rule #2); `common` itself may never import a domain module — that would create exactly the cross-module cycle rule #13 forbids, just one hop removed. A concept lands here only once it clears the bar in `references/placement.md#when-duplication-is-correct` (three or more modules need it, it's stable, and divergence would be a bug) — it is a promotion, not a first draft. `common` keeps the same shape as any module (its own `constants.py`, `public.py`, `exceptions.py` if it needs one) and the same size discipline as rule #12; the moment it wants a `router.py` or a table of its own, what's living there was a domain concept with an owner all along, not something genuinely shared.

**18. Within a module, imports run one direction only.** `constants.py`/`config.py` → `exceptions.py`/`schemas.py`/`models.py`/`events.py` → `rules.py`/`utils/` → `repository.py`/`uow.py` → `services/*.py` → `dependencies.py` → `router.py` → `public.py`. A file only imports from a file earlier in that chain; two files in the same module never import each other, and nothing points back up it — the same principle as rule #13, spelled out file by file in `references/architecture.md#intra-module-import-order`.

## Deciding how far to go

Match the ceremony to the size — over-structuring is as damaging as under-structuring and much easier to do by accident.

- **Under ~15 endpoints**: one module, `--minimal`, skip the unit of work.
- **Multiple domains and a team**: the full structure.
- **Only add the queue** when there is real async work or real cross-module eventing. The in-process `EventBus` covers the rest.
- **Only add the outbox** when losing an event has business consequences.
- **The `Abstract*` repository/uow/use-case contracts (rule #15) are the default, not a judgment call** — they cost one extra class per file and buy a Fake-based unit test with no database. `--minimal` still generates `repository.py`'s `Abstract{X}Repository`; it only skips `uow.py`.

Say so plainly when a request would push past what the project needs. Suggesting the smaller version is more useful than silently building the bigger one.

## Writing style in generated code

- Docstrings and logs in English; one docstring per class and function, no inline `#` comments.
- Type hints everywhere; anything crossing a cache boundary is frozen.
- `async` all the way down — a sync driver in `async def` blocks the event loop.
- Never return ORM models from endpoints. Lazy loading on a detached instance raises `MissingGreenlet`, and ORM models leak fields never meant to be public.

## Reference files

Read the one that matches the task.

- `references/placement.md` — where each kind of code belongs, and the failure modes of getting it wrong
- `references/architecture.md` — layer responsibilities, dependency direction, testing
- `references/layer-examples.md` — every layer's real code side by side: `Abstract*` contracts, class-grouped constants/rules/utils, schema-level validation, the `@database`/`@helper`/`@rule`/`@use_case`/`@facade` markers, and the Fake-based unit test they make possible
- `references/caching.md` — versioned keys, singleflight, invalidation across related entities
- `references/messaging.md` — topology, outbox, idempotent consumers, retry
- `references/api-contract.md` — camelCase wire format, the `ApiResponse` envelope (REST and SSE), error codes as i18n keys
- `references/deployment.md` — env file matrix, the two compose files, Makefile, startup scripts, seed scripts, deploy checklist
- `references/rbac.md` — org/department-scoped roles and permissions, the `require_permission` dependency pattern, why role strings are never hardcoded
- `references/logging.md` — request_id vs correlation_id, propagation across the queue and to other services, redaction, business context binding
- `references/checklist.md` — pre-production review

## Verify before handing over

A structure that doesn't import is worse than no structure:

```bash
uv run ruff check app && uv run ruff format --check app
uv run lint-imports
python scripts/check_module_boundaries.py --strict
uv run python -c "from app.main import app; print(len(app.openapi()['paths']), 'paths')"
```
