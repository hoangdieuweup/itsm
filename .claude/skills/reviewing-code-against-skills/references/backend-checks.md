# Backend Checks — Python / FastAPI / SQLAlchemy

Run the tools first (`ruff check`, `ruff format --check`, `lint-imports`, `bandit -r app`), then check for these — none of the four tools above catch them.

## File and function size
`ruff check` already flags function complexity over 15 as `C901` if the project's `pyproject.toml` enables it (`select = [..., "C90"]` + `[tool.ruff.lint.mccabe] max-complexity = 15`) — if it's missing from a changed `pyproject.toml`, flag that as a gap, don't silently skip the check. File length isn't something `ruff` measures — run `wc -l` on each changed file and flag anything over ~500-600 lines. The fix in both cases is a subpackage (`repository/`, `router/`), never a flatter file — see the governing skill's `references/architecture.md` for the split pattern it expects.

## N+1 queries
Lazy-loading a relationship inside a loop issues one query per iteration instead of one query total.

```python
# N+1 — one query per user to load .orders
users = (await session.execute(select(User))).scalars().all()
for user in users:
    print(user.orders)
```
```python
# One query — the relationship is loaded eagerly, in the same round trip
from sqlalchemy.orm import selectinload

users = (
    await session.execute(select(User).options(selectinload(User.orders)))
).scalars().all()
```
Flag: any `for`/list-comprehension loop over query results that accesses a relationship attribute (`.orders`, `.items`, a foreign-key-backed attribute) without `selectinload`/`joinedload` on the original query. `selectinload` for one-to-many/many-to-many, `joinedload` for one-to-one/many-to-one.

Also flag a repository method called inside a loop (`for id in ids: await repo.get(id)`) — batch it (`get_many(ids)` with a single `WHERE id IN (...)`) instead.

## Database ownership rules
If the governing skill is `fastapi-modular-scaffold`, its non-negotiable rules directly bear on this:
- **One table, one owning module.** A `SELECT`/`JOIN` touching another module's table is a violation — the read should go through that module's `public.py` facade, composed in the service layer instead of joined in SQL.
- **Invalidate after commit, never before.** `mark_stale()`/cache invalidation calls before `session.commit()` let a concurrent reader repopulate the cache from pre-commit state. Flag any invalidation call that isn't inside a `uow.commit()`-style post-commit hook.
- **Pools live in `lifespan.py`.** A `create_async_engine(...)` or a client constructor called from inside a request path (a dependency, a route, a service) instead of at startup is a pool-per-request bug.
- **Never return ORM models from endpoints.** A route handler returning a SQLAlchemy model instance instead of a Pydantic schema will raise `MissingGreenlet` on lazy access after the session closes, and leaks fields never meant to be public. Flag any router function whose return annotation or return statement is a `models.py` class.
- **Something has to commit.** A repository calling only `flush()` (correct, per the rule above) with no `uow.py` in that module and no commit-on-success in `app/database.py`'s `get_session` means nothing ever persists past the request — a real bug, not a style issue, and one that only shows up when a router integration test actually asserts a row survives past the request that created it. If a module is `--minimal` (no `uow.py`), confirm `get_session` commits on a clean return and rolls back on exception.

If the governing skill is something else, read its own rules section for the equivalent constraints before falling back to the ones above — don't assume this project uses the same conventions.

## Hardcoded roles / unscoped permission checks
If the project has an access-control module following `fastapi-modular-scaffold`'s `references/rbac.md`, flag:
- `if user.role == "..."`, `if "admin" in user.roles`, or any direct role-string comparison in a router or service — the fix is a `Permission` row and a `require_permission(resource, action)` dependency, not a special case for that string.
- A `role` column directly on the user/identity table instead of a scoped `user_role` grant (`user_id`, `organization_id`, `role_id`) — can't express "different role per organization," which is usually why the check above exists in the first place.
- A permission check missing an `organization_id` (or equivalent scope) argument — an unscoped check is a global-role mistake even if the schema underneath is scoped correctly.

## Suppression comments without a reason
`ruff check` reports `PGH003`/`PGH004` for a blanket `# type: ignore`/`# noqa` (no specific code), if the project's `pyproject.toml` selects them — flag it as a gap if a changed `pyproject.toml` doesn't. That only catches the mechanical half. Also flag, by reading the line yourself, any `# noqa: CODE`/`# type: ignore[code]` with no `-- reason` text after it — a specific code without a stated reason still doesn't say *why* the violation is acceptable here. A suppression comment is a decision that has to survive whoever wrote it leaving the team.

## Local imports and circular imports
`ruff check` reports `PLC0415` for any import inside a function body, if the project's `pyproject.toml` enables it — flag it as a gap if a changed `pyproject.toml` doesn't select `PLC0415`. A local import existing specifically to dodge a circular-import crash is not a pass — it's evidence of a real cycle between two files, which is the actual finding to report. Trace which two files import each other and name both in the finding; the fix is moving the shared piece down into `constants.py`/`schemas.py` or up into `public.py`, not keeping the local import.

## Abstract contracts (repository / uow / use case)

If the governing skill is `fastapi-modular-scaffold`, its `references/layer-examples.md` is the source of truth — read it, don't assume the shape from memory. Flag:
- A `{X}Repository`/`{X}UnitOfWork` class with no matching `Abstract{X}Repository`/`Abstract{X}UnitOfWork` extending the root's `AbstractRepository`/`AbstractUnitOfWork` (`app/repository.py`/`app/uow.py`) — the concrete class alone isn't the contract.
- A `services/*.py` class that doesn't extend `AbstractUseCase` (`app/use_case.py`).
- A service, `dependencies.py` consumer function, or `public.py` facade whose constructor/parameter is typed against the *concrete* class (`{X}Repository`) instead of the `Abstract{X}Repository`/`Abstract{X}UnitOfWork` contract — this is the actual Dependency Inversion violation, not just a style nit: it means the class can't be swapped for a `Fake{X}Repository` in a unit test without editing the file. `dependencies.py`'s own construction functions (`get_uow`, and `get_repo` in a `--minimal` module) are the one legitimate exception — they're the composition root and are supposed to name the concrete class.
- A module with a write use case but no `tests/<module>/test_services.py` — the payoff of the abstract contract is a Fake-based unit test; a module that extends `AbstractUseCase` but never exercises it against a Fake isn't getting the benefit it paid the extra class for.

## No bare constants or helper functions outside a class

If the governing skill is `fastapi-modular-scaffold`, flag any of these inside `constants.py`, `rules.py`, or a file under `utils/`:
- A bare `NAME = value` sitting above (or beside) a class in the same file — it should be a class attribute (`Limits.MAX_NAME_LENGTH`, not a loose `MAX_NAME_LENGTH`).
- A bare `def helper(...)` not attached to any class — it should be a `@staticmethod` on a class named for the concern (`TextUtils.normalize_name`, not a bare `normalize_name`).
- A flat `utils.py` file instead of a `utils/` package (`utils/__init__.py` re-exporting one class per concern file) — flag this once the file holds more than one concern's worth of helpers, the same threshold as the file-size rule.

This does **not** apply to `router.py`, `dependencies.py`, `lifespan.py`, `middleware.py`, or a seed script's `run()` — those stay plain functions FastAPI's `Depends()` (or `if __name__ == "__main__":`) calls directly; don't flag a dependency provider or a route handler for being a bare function.

## Schema-level validation

If the governing skill is `fastapi-modular-scaffold`, flag:
- A schema's `field_validator` reimplementing a check that already exists in that module's `rules.py`/`utils/` instead of calling it — two implementations of "what makes a name valid" drift the moment one changes and the other doesn't.
- A router or service manually re-parsing/re-validating a field a schema's `field_validator` already covers, when the intent was for the schema to be the single wire-boundary check (defensive re-validation inside a use case that's also callable outside HTTP is fine; duplicating the same check inside the router is not).
- A project with schema `field_validator`s but no `RequestValidationError` handler in `main.py` — without it, a validation failure returns FastAPI's default `{"detail": [...]}`, not the `{success, data, error}` envelope every other endpoint returns. This is a direct violation of the API contract section below, not a separate concern.

## API contract: envelope, camelCase, error codes
If the governing skill is `fastapi-modular-scaffold`, its `references/api-contract.md` is the source of truth — read it, don't assume the shape from memory. Flag:
- A router endpoint whose `response_model`/return value is a bare schema (`{Cls}Read`, `Page[...]`) instead of `ApiResponse[...]` — every endpoint returns the `{success, data, error}` envelope, no exceptions except `/health`.
- A route that builds an error response by hand (`JSONResponse(content={"detail": ...})`, a raw `dict`) instead of raising an `AppError` subclass and letting the two handlers in `main.py` build the envelope.
- A schema that doesn't inherit `CustomModel`/`FrozenModel` (or `Page`) — it won't get the camelCase `alias_generator`, so its wire format silently reverts to snake_case while every sibling schema is camelCase.
- `ErrorPayload.message` (or any exception's `.message`) interpolated into a string shown anywhere a translated string should appear — that's the non-localized fallback, not user-facing copy in an i18n-aware system. `code` is the key; see the frontend's `references/i18n-and-errors.md` for the other half of this contract.

## Security (beyond what bandit flags)
- Secrets read from anywhere other than `Config`/`BaseSettings` (a hardcoded API key, a token committed as a string literal).
- User input reaching a raw SQL string via f-string/`.format()`/`%` instead of a parameterized query or the ORM.
- A `Literal`/`Enum`-shaped setting (deployment environment, log level, feature flag) typed as a bare `str` — see `LOG_LEVEL`/`Environment` in `fastapi-modular-scaffold` for the pattern: a closed value set should fail at settings-load time via an enum, not at first use.
- Sensitive fields (password, token, authorization header, PII) reaching a log call without going through a redaction processor.
