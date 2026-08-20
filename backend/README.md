# itsm

Modular FastAPI service. Every module owns its own constants, enums, config,
exceptions and helpers. Integrations are modules too, not a flat utility folder.

## Domain modules

- `app/auth/`

Each contains: `constants.py` (enums, error codes), `config.py` (module settings),
`exceptions.py` (concrete errors), `schemas.py`, `models.py`, `rules.py` (pure
decisions), `utils.py` (non business helpers), `repository.py`, `uow.py`,
`services/` (one file per use case), `dependencies.py`, `router.py`, `public.py`.

## Integration modules

- `app/integrations/cache/`
- `app/integrations/queue/`
- `app/integrations/storage/`

Each contains `client.py`, `config.py`, `constants.py`, `exceptions.py` and
`dependencies.py`. They own no tables and expose no routes.

## Root

`app/` holds mechanism only: the `AppError` base, `CustomModel`, the database
connection, pagination and the event bus. No business concept lives here.

## Running

```bash
cp .env.example .env
uv sync
docker compose up -d
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head
```

## Rules

1. A module reaches another only through its `public.py`. `lint-imports` enforces it.
2. Constants, enums, config, exceptions and helpers live in the module that owns the concept.
3. The root holds mechanism, never a business concept. If `app/exceptions.py` starts
   naming domain entities, the boundary has already leaked.
4. `rules.py` holds pure decisions; `utils.py` holds formatting and normalization.
5. Cross module imports name the module: `from app.identity import constants as identity_constants`.
6. Invalidate the cache after commit, never before.
7. Pools are created in `lifespan.py`, never in a dependency.

## Checks

```bash
uv run ruff check app && uv run ruff format --check app
uv run mypy app
uv run lint-imports
uv run pytest
```
