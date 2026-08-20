# Architecture reference

## Dependency direction

```
router -> dependencies -> service -> repository -> models
             |               |            |
             |         rules, utils   integrations/cache
             |
   binds Abstract* (root) to the concrete class — the only place that does
```

Modules depend on the root and on `integrations/`. The root and integrations
depend on neither. Domain modules reach each other only sideways, through
`public.py`.

`service` depends on `Abstract{X}Repository`/`Abstract{X}UnitOfWork` — contracts
owned by the root (`app/repository.py`, `app/uow.py`), not on the concrete
SQLAlchemy class `repository.py` also defines. `dependencies.py` is the
composition root: the one place a concrete class is named and constructed.
See `references/layer-examples.md` for the full worked example, including why
(Dependency Inversion, Fake-based unit tests, a `TypeError` instead of a
silent gap when a concrete class forgets a method).

Nothing points back up. `rules.py` imports nothing from the project. `repository.py` never imports a service. If an import needs to go upward, the logic is sitting in the wrong layer.

Every import stays at the top of the file (`ruff`'s `PLC0415` enforces this) and no two files import each other. If a function-body import shows up to dodge a circular-import crash, that crash is the actual signal — don't silence it with a local import. Find the piece both files need and move it down a layer (a shared type into `constants.py`/`schemas.py`) or up into `public.py`, so the dependency only ever points one way again.

## Layer responsibilities

| File | Owns | Must not |
|---|---|---|
| `router.py` | HTTP shape, status codes, response_model | Business rules, DB access, catching domain errors |
| `dependencies.py` | Wiring via `Depends`, path validation | Logic of any kind |
| `services/*.py` | One use case, orchestration, transaction scope | SQL, Redis commands, HTTP concepts |
| `rules.py` | Pure decisions | Any I/O — that is what makes it testable without mocks |
| `utils.py` | Formatting and normalization | Business decisions |
| `constants.py` | Enums, limits, error codes | Anything requiring an import from another module |
| `config.py` | Settings only this module reads | Settings the process needs to start |
| `exceptions.py` | Concrete errors of this module | Base classes, which live at the root |
| `repository.py` | `Abstract{X}Repository` contract + the SQLAlchemy class implementing it | Business decisions, calling other modules |
| `uow.py` | `Abstract{X}UnitOfWork` contract + the transaction boundary, deferred invalidation | Queries |
| `schemas.py` | Data shapes crossing layers and Redis; field-level validation/serialization for the fields it owns | Business decisions needing I/O (a DB lookup, a cross-entity state check) |
| `public.py` | The contract other modules consume | Exposing ORM models or repositories |

## Why the facade matters

Importing another module's repository directly looks harmless and is the single most common cause of a monolith that cannot be split. Once `billing` queries the `users` table, extracting `identity` means hunting every query in the codebase. With a facade, extraction means swapping one class for an HTTP client.

The facade is also the natural place to later add caching, permission checks or rate limits for cross-module access.

## Composition instead of JOIN

```python
user = await self._users.get_by_id(user_id)
tenant = await self._tenancy.get_tenant(user.tenant_id)
```

Two cached reads instead of one JOIN. The gain is invalidation: a tenant update bumps one key and every user of that tenant sees fresh data. With a cached JOIN blob you would have to find and invalidate every affected composite key, and eventually you will miss one.

When the N+1 shape appears while composing a list, batch it — give the facade a `get_many(ids)` backed by `WHERE id = ANY(...)` or Redis `MGET`, and call it once instead of per row.

## Transactions

The unit of work owns the boundary; use cases open it, repositories join it. A repository calls `flush()`, never `commit()` — committing inside a repository makes multi-step use cases impossible to keep atomic.

```python
async with self._uow:
    await self._uow.users.update_email(user_id, email)
    self._uow.mark_stale("user", user_id)
    await self._uow.commit()
```

Publish events after leaving the block. Holding a transaction open across a network call ties DB connection lifetime to broker latency, which is how pools get exhausted under load.

Note that SQLAlchemy's `AsyncSession` is already a unit of work and identity map. Wrap it only to add behaviour it lacks — here, invalidation ordering. Wrapping it merely to own a class named `UnitOfWork` adds a layer with nothing in it.

A `--minimal` module has no `uow.py`, so nothing ever calls `commit()` on its behalf — `app.database.get_session` is the transaction boundary instead: it commits once the request completes without raising, and rolls back if it does. A module with `uow.py` still goes through the same `get_session`, so its explicit `uow.commit()` runs first and `get_session`'s own commit afterward is a no-op on an already-clean transaction, not a second write. This was found, not assumed: an earlier version of this template had `get_session` do neither, which meant a `--minimal` module's `repository.create()` — correctly calling only `flush()`, never `commit()` — silently never persisted anything past the request. Caught by actually running the generated project's own router tests against a real Postgres container, not by inspection.

## Errors

Domain layers raise `AppError` subclasses carrying a stable `code` and `status_code`; `main.py` maps them once. Services never import `HTTPException` — that ties the domain to HTTP and breaks reuse from workers and CLI entry points.

## Testing

### Where tests live
`tests/` sits outside `app/`, mirroring its module layout — `tests/identity/`, `tests/billing/`, one folder per domain module, not colocated inside the module and not one flat file. This is the standard Python convention (keeps test code out of the shipped package) while still respecting module ownership: `tests/identity/` only ever imports `app.identity.*`. `lint-imports` doesn't scan `tests/` at all (`root_package = app`), so a test may reach into a module's internals that other modules may not.

```
tests/
├── conftest.py           # the Postgres container, the HTTP client, table truncation between tests
├── identity/
│   ├── test_rules.py     # pure unit tests — no fixtures
│   ├── test_services.py  # use-case unit tests against a Fake repository/uow — no database
│   └── test_router.py    # integration tests — uses the client fixture, real Postgres
└── billing/
    ├── test_rules.py
    ├── test_services.py
    └── test_router.py
```

Naming: `test_<file>.py` mirrors the source file it exercises (`rules.py` → `test_rules.py`), `test_<behavior>` functions, no test class wrappers — pytest doesn't need them and they add indirection for no benefit here.

### What to test where
- `rules.py` — plain unit tests, no fixtures, no mocks. Push branching logic here so most tests stay this cheap.
- Use cases (`services/*.py`) — a `Fake{X}Repository`/`Fake{X}UnitOfWork` extending the module's `Abstract*` contract, constructed directly with no fixtures beyond the fake itself. This is the payoff of typing services against `Abstract{X}Repository`/`Abstract{X}UnitOfWork` instead of the concrete SQLAlchemy class (see `references/layer-examples.md`) — every branch of a use case runs at memory speed, with no container to start. Not a replacement for the router test below; it answers a different question ("does the logic work?", not "does it work against a real database and a real transaction?").
- Repositories — integration tests against a real Postgres container (`tests/conftest.py`'s `postgres_url`/`engine` fixtures, via `testcontainers`). Mocking a repository to test a repository tests nothing.
- Routers — the `client` fixture (`httpx.AsyncClient` + `ASGITransport`) against the real app, with `get_session` overridden; assert status and payload shape only. This is the only layer that also exercises `main.py`'s exception handlers, including the `RequestValidationError` → envelope handler a schema's `field_validator` failure goes through — see `references/api-contract.md`.

`dependency_overrides` still matters for router-level integration tests (swapping the real Postgres container in, the way `tests/conftest.py` does) — it just doesn't replace the value of a Fake at the use-case level, which is what makes a fast, fixture-free unit test possible in the first place.

### Isolation
`ASGITransport` runs the app in its own `anyio` task so it can stream the response — a connection opened in the fixture's task and handed to the app would be used from a different task than the one that created it, which asyncpg rejects. So `get_session` is overridden with a factory that opens a fresh session *inside whichever task calls it*, never a single shared connection passed across the boundary. Isolation between tests then comes from truncating every table (`reversed(Base.metadata.sorted_tables)`, FK-safe order) once the client is done, against one Postgres container shared for the whole run — one container start instead of one per test.

pytest-asyncio needs `asyncio_default_fixture_loop_scope` **and** `asyncio_default_test_loop_scope` both set to `"session"` (both are in `pyproject.toml`) — setting only the fixture scope runs fixtures and test functions on two different event loops, which is its own, unrelated source of the same "attached to a different loop" error.

A module-specific fixture (a factory, a seeded row) goes in `tests/<module>/conftest.py`, not the root one — the root `conftest.py` stays project-wide mechanism, same rule as `app/config.py` versus a module's own `config.py`.

## Adding a module

1. `python scripts/scaffold.py --add-module <name>`
2. Define tables in `models.py`, generate a migration
3. Write `constants.py`, `schemas.py` and `rules.py` first — settling the data shape and the decisions before the plumbing keeps the plumbing honest
4. Repository, then use cases, then router
5. Export the minimum through `public.py`
6. Include the router in `main.py`, add the module to `.importlinter`, run `lint-imports`

## Keeping files and functions small

A file over ~500-600 lines or a function over cyclomatic complexity 15 (enforced by `ruff`'s `C901`) is a sign the module has more than one concept living in one place — the fix is a subpackage, never a flatter file.

`services/` already models the pattern to reuse everywhere else: one file per use case instead of one `services.py` growing forever. Apply the same split to any other file that outgrows its budget:

```
# router.py grew past readable size because the module gained many endpoints
router/
├── __init__.py     # re-exports and assembles the APIRouter other files register on
├── list.py
├── create.py
└── detail.py

# repository.py grew because the table gained many query shapes
repository/
├── __init__.py     # the Repository class, thin, composes the pieces below
├── reads.py
└── writes.py
```

A function past complexity 15 is almost always doing more than one job: extract the branching into `rules.py` (if it's a decision) or split it into smaller private functions with names that say what each branch is for. Don't suppress the `ruff` warning — that hides the signal instead of acting on it.

## No bare constants or helper functions outside a class

A value or a helper function still lives in the file that owns it — `constants.py` for a limit, `utils/`
for a formatter — and still gets imported from there where it's used; that part hasn't changed. What's
different is that nothing sits at module level *within* that file: a limit is a class attribute
(`CatalogLimits.MAX_NAME_LENGTH`), a formatter is a `@staticmethod` (`CatalogTextUtils.normalize_name`),
grouped by concern. `utils.py` is a package (`utils/__init__.py` re-exporting, `utils/text.py` etc.), one
file and one class per concern, the same way `services/` is one file per use case.

This does not reach into `router.py`, `dependencies.py`, or `lifespan.py` — a FastAPI dependency
provider is a plain function `Depends()` calls directly, which is a framework entry point, not the
scattered helper this rule targets. See `references/layer-examples.md` for the full worked example,
including the `@database`/`@helper`/`@rule`/`@use_case`/`@facade` decorators in `app/markers.py` that
tag each class with its role.

## Configuration

Settings are split the same way everything else is. `app/config.py` holds what the process needs to start — database URL, environment, CORS. Each module holds its own settings in its own `config.py` with an env prefix, so `IDENTITY_JWT_SECRET` is visibly owned by identity.

The reason is the same as for constants: a single global `Config` accumulates every setting any module ever needed, and reading it tells you nothing about who uses what. Splitting it also means a module carries its configuration with it if extracted.

Validate at import so a missing variable fails at startup rather than at 3am on the first request that touches it. Never call `os.getenv` outside a `config.py`.
