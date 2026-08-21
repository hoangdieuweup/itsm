"""Templates for project level files."""


def pyproject(name: str, features: list[str]) -> str:
    """Render pyproject.toml with only the dependencies that are used."""
    deps = [
        '"fastapi>=0.115"',
        '"uvicorn[standard]>=0.32"',
        '"pydantic>=2.9"',
        '"pydantic-settings>=2.6"',
        '"sqlalchemy[asyncio]>=2.0"',
        '"asyncpg>=0.30"',
        '"alembic>=1.14"',
        '"structlog>=24.4"',
        '"gunicorn>=23.0"',
    ]
    if "cache" in features:
        deps.append('"redis>=5.2"')
    if "queue" in features:
        deps.append('"aio-pika>=9.5"')
    if "storage" in features:
        deps.append('"aioboto3>=13.2"')
    if "tracing" in features:
        deps += [
            '"opentelemetry-api>=1.27"',
            '"opentelemetry-sdk>=1.27"',
            '"opentelemetry-exporter-otlp-proto-grpc>=1.27"',
            '"opentelemetry-instrumentation-fastapi>=0.48b0"',
        ]

    body = ",\n    ".join(deps)
    return f'''
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    {body},
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "ruff>=0.8",
    "mypy>=1.13",
    "import-linter>=2.1",
    "testcontainers[postgres]>=4.8",
]

[tool.ruff]
line-length = 110
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "ASYNC", "C90", "PLC0415", "PGH003", "PGH004"]
ignore = [
    "B008",
    "N818",
]

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.ruff.lint.mccabe]
max-complexity = 15

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.11"
plugins = ["pydantic.mypy"]
warn_unused_ignores = true
'''


def compose(name: str, features: list[str]) -> str:
    """Render docker-compose.yml for the selected infrastructure."""
    services = [f'''
  api:
    build: .
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    command: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./app:/srv/app

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: {name}
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 10''']

    volumes = ["  pgdata:"]

    if "cache" in features:
        services.append('''
  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 10''')

    if "queue" in features:
        services.append('''
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitdata:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_running"]
      interval: 10s
      retries: 10

  worker:
    build: .
    env_file: .env
    depends_on:
      rabbitmq:
        condition: service_healthy
    command: uv run python -m app.worker
    volumes:
      - ./app:/srv/app''')
        volumes.append("  rabbitdata:")

    if "storage" in features:
        services.append('''
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - miniodata:/data''')
        volumes.append("  miniodata:")

    return "services:" + "".join(services) + "\n\nvolumes:\n" + "\n".join(volumes) + "\n"


def compose_prod(name: str, features: list[str]) -> str:
    """Render docker-compose.prod.yml.

    Same services as docker-compose.yml, prod-flavored: no bind mount, no
    --reload (the image's own CMD — scripts/start.sh, Gunicorn — runs as-is),
    a separate env file so prod credentials are never in the dev one, a
    distinct host port so this can run alongside a non-prod stack on the same
    host, and infra services (postgres/redis/rabbitmq/minio) are not exposed
    to the host at all — only api/worker need to be reachable from outside.
    """
    services = [f'''
  api:
    build: .
    env_file: .env.prod
    ports:
      - "8001:8000"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: {name}_prod
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 10
    restart: unless-stopped''']

    volumes = ["  pgdata:"]

    if "cache" in features:
        services.append('''
  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 10
    restart: unless-stopped''')

    if "queue" in features:
        services.append('''
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    volumes:
      - rabbitdata:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_running"]
      interval: 10s
      retries: 10
    restart: unless-stopped

  worker:
    build: .
    env_file: .env.prod
    depends_on:
      rabbitmq:
        condition: service_healthy
    command: ["./scripts/start-worker.sh"]
    restart: unless-stopped''')
        volumes.append("  rabbitdata:")

    if "storage" in features:
        services.append('''
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - miniodata:/data
    restart: unless-stopped''')
        volumes.append("  miniodata:")

    return (
        f"name: {name}-prod\n\nservices:"
        + "".join(services)
        + "\n\nvolumes:\n"
        + "\n".join(volumes)
        + "\n"
    )


def start_sh() -> str:
    """Render scripts/start.sh: the API server, Gunicorn managing Uvicorn workers."""
    return '''#!/bin/sh
set -e

if [ -z "$WEB_CONCURRENCY" ]; then
    if [ "$ENV" = "prod" ]; then
        WEB_CONCURRENCY=4
    else
        WEB_CONCURRENCY=2
    fi
fi

exec gunicorn app.main:app \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --workers "$WEB_CONCURRENCY" \\
    --bind 0.0.0.0:8000 \\
    --timeout 120 \\
    --access-logfile - \\
    --error-logfile -
'''


def start_worker_sh() -> str:
    """Render scripts/start-worker.sh: the queue consumer process."""
    return '''#!/bin/sh
set -e

exec python -m app.worker
'''


def makefile(has_queue: bool) -> str:
    """Render the Makefile: one place for the commands every environment needs."""
    worker_targets = (
        '''
worker-logs: ## Tail the worker's logs
\tdocker compose -f $(COMPOSE_FILE) logs -f worker
'''
        if has_queue
        else ""
    )
    return f'''.PHONY: help up down logs migrate seed worker-logs

ENV ?= stg

ifeq ($(ENV),prod)
COMPOSE_FILE := docker-compose.prod.yml
else
COMPOSE_FILE := docker-compose.yml
endif

help: ## List available commands
\t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {{FS = ":.*?## "}}; {{printf "%-15s %s\\n", $$1, $$2}}'

up: ## Build and start (ENV=prod for production)
\tdocker compose -f $(COMPOSE_FILE) up -d --build

down: ## Stop and remove containers
\tdocker compose -f $(COMPOSE_FILE) down

logs: ## Tail the API's logs
\tdocker compose -f $(COMPOSE_FILE) logs -f api

migrate: ## Run Alembic migrations
\tdocker compose -f $(COMPOSE_FILE) exec api alembic upgrade head

seed: ## Run every seed script under app/seeds/
\tdocker compose -f $(COMPOSE_FILE) exec api sh -c "for m in app/seeds/seed_*.py; do python -m $$(echo $$m | sed 's#/#.#g; s#\\.py##'); done"
{worker_targets}'''


def dockerfile() -> str:
    """Render the application Dockerfile, installed and run through uv."""
    return '''
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \\
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts
RUN uv sync --no-dev && chmod +x scripts/*.sh

ENV PATH="/srv/.venv/bin:${PATH}"

RUN useradd -m appuser && chown -R appuser /srv
USER appuser

EXPOSE 8000
CMD ["./scripts/start.sh"]
'''


def env_example(features: list[str]) -> str:
    """Render .env.example listing every variable the app reads.

    Copy to .env for local dev. For docker-compose.prod.yml, copy to .env.prod
    instead and give every secret a value that differs from dev/stg — see
    references/deployment.md. Neither .env nor .env.prod is ever committed.
    """
    lines = [
        "ENV=dev",
        "LOG_LEVEL=INFO",
        "DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/app",
        "DB_POOL_SIZE=20",
        "CORS_ORIGINS=[]",
        "",
        "# DOCS_USERNAME / DOCS_PASSWORD only matter when ENV=stg — they gate /docs, /redoc, /openapi.json",
        "DOCS_USERNAME=",
        "DOCS_PASSWORD=",
    ]
    if "cache" in features:
        lines += ["", "CACHE__URL=redis://redis:6379/0", "CACHE__DEFAULT_TTL=300"]
    if "queue" in features:
        lines += ["", "QUEUE__URL=amqp://guest:guest@rabbitmq:5672/", "QUEUE__PREFETCH=20"]
    if "storage" in features:
        lines += ["", "STORAGE__ENDPOINT=http://minio:9000", "STORAGE__BUCKET=app", "STORAGE__ACCESS_KEY=minioadmin", "STORAGE__SECRET_KEY=minioadmin"]
    if "tracing" in features:
        lines += ["", "TRACING__ENABLED=true", "TRACING__OTLP_ENDPOINT=http://localhost:4317"]
    return "\n".join(lines) + "\n"


def import_linter(modules: list[str], integrations: list[str]) -> str:
    """Render the contract that keeps module boundaries real."""
    sources = "\n".join(f"    app.{m}" for m in modules)
    forbidden = "\n".join(
        f"    app.{m}.repository\n    app.{m}.models\n    app.{m}.uow\n    app.{m}.services"
        for m in modules
    )
    layers = "\n".join(f"    app.{m}" for m in modules)
    integ_layers = "\n".join(f"    app.integrations.{i}" for i in integrations)
    return f'''
[importlinter]
root_package = app

[importlinter:contract:module-facades]
name = Domain modules reach each other only through public.py
type = forbidden
source_modules =
{sources}
forbidden_modules =
{forbidden}
allow_indirect_imports = True

[importlinter:contract:root-is-mechanism]
name = The root holds mechanism and never imports a module
type = forbidden
source_modules =
    app.config
    app.constants
    app.exceptions
    app.models
    app.database
    app.pagination
    app.events
    app.middleware
    app.logging_config
    app.docs
    app.repository
    app.uow
    app.use_case
    app.markers
    app.retry
forbidden_modules =
{layers}
{integ_layers}

[importlinter:contract:integrations-are-leaves]
name = Integrations never import a domain module
type = forbidden
source_modules =
{integ_layers}
forbidden_modules =
{layers}
'''


def alembic_ini() -> str:
    """Render alembic.ini."""
    return '''
[alembic]
script_location = migrations
prepend_sys_path = .
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(slug)s

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
'''


def alembic_env(modules: list[str]) -> str:
    """Render migrations/env.py importing every module's models."""
    imports = "\n".join(
        f"from app.{m} import models as {m}_models  # noqa: F401 -- registers {m}'s tables on Base.metadata for autogenerate"
        for m in modules
    )
    return f'''
"""Alembic environment importing every module so autogenerate sees all tables."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.config import settings
from app.core.database import Base
{imports}

config = context.config
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection) -> None:
    """Configure and execute migrations on an open connection."""
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {{}}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    """Emit SQL without connecting to a database."""
    context.configure(url=str(settings.DATABASE_URL), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
'''


def alembic_mako() -> str:
    """Render the migration script template."""
    return '''
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''


def readme(name: str, modules: list[str], features: list[str]) -> str:
    """Render the project README."""
    mod_list = "\n".join(f"- `app/{m}/`" for m in modules)
    feat_list = "\n".join(f"- `app/integrations/{f}/`" for f in features) or "- none"
    return f'''
# {name}

Modular FastAPI service. Every module owns its own constants, enums, config,
exceptions and helpers. Integrations are modules too, not a flat utility folder.

## Domain modules

{mod_list}

Each contains: `constants.py` (enums, error codes), `config.py` (module settings),
`exceptions.py` (concrete errors), `schemas.py`, `models.py`, `rules.py` (pure
decisions), `utils.py` (non business helpers), `repository.py`, `uow.py`,
`services/` (one file per use case), `dependencies.py`, `router.py`, `public.py`.

## Integration modules

{feat_list}

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
3. The root holds mechanism, never a business concept. If `app/core/exceptions.py` starts
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
'''
