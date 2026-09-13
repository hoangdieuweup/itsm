# ITSM — DevOps Control Panel

Internal control panel for running projects and their environments. It covers who can access what, Cloudflare DNS and tunnels, Grafana Loki logs and alerts, incidents and notifications. Users sign in with DX Core SSO.

The repository holds two apps:

- [`backend/`](backend/): a FastAPI API, plus a RabbitMQ worker and a scheduler
- [`frontend/`](frontend/): the Next.js web app

## Features

| Area | What it covers |
|---|---|
| Projects | Projects, their environments, external links (Jira, Git), members and project-scoped roles |
| Access control | Global roles and permissions, per-project roles, a break-glass admin account |
| Cloudflare | Accounts with encrypted API tokens, account managers, DNS records, tunnels and their public hostnames, traffic stats |
| Observability | Per-environment Loki configuration, log search and live tail, alert rules, incidents (acknowledge and resolve), alert webhooks from Cloudflare and Alertmanager |
| Drift reconciliation | A scheduled job that re-checks DNS and tunnel state in Cloudflare and opens an incident when something changed outside the app |
| Notifications | Email (SMTP), Telegram and Base.vn channels |
| Audit log | User actions recorded in MongoDB |

The UI is available in Vietnamese (default) and English.

## Tech stack

| Part | Technologies |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, Pydantic 2, structlog, Gunicorn + Uvicorn |
| Data and messaging | PostgreSQL 16, Redis 7, RabbitMQ 3.13, MongoDB 7, MinIO (S3-compatible storage) |
| External services | DX Core (OAuth2 + PKCE), Cloudflare API, Grafana Loki, SMTP, Telegram, Base.vn |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, TanStack Query 5, Zod 4, next-intl 4, Tailwind CSS 4, shadcn/ui |
| Tooling | uv, Ruff, import-linter, pytest + testcontainers, pnpm, ESLint 9 + eslint-plugin-boundaries, Vitest |

## Repository layout

```text
.
├── backend/
│   ├── app/
│   │   ├── core/           shared mechanism: database, errors, pagination, events, security
│   │   ├── integrations/   clients for external systems: cache, queue, storage, mongo, cloudflare, loki, dx_core, email, telegram, base_vn
│   │   ├── modules/        business modules: auth, rbac, users, projects, audit, cloudflare, observability, notifications, common
│   │   ├── seeds/          seed_rbac.py, seed_admin.py
│   │   ├── main.py         API entry point
│   │   ├── worker.py       RabbitMQ consumer
│   │   └── scheduler.py    periodic drift reconciliation
│   ├── alembic/            database migrations
│   ├── scripts/            start scripts and the module boundary checker
│   ├── tests/
│   ├── docker-compose.yml        local stack
│   ├── docker-compose.prod.yml   production stack
│   └── Makefile
├── frontend/
│   ├── src/
│   │   ├── app/            routes only, under [locale]/
│   │   ├── modules/        feature workflows: projects, users, roles, cloudflare-*, alerting, incidents, log-viewer, notifications, audit-log, dashboard, auth
│   │   ├── entities/       domain schemas, query keys and read hooks
│   │   ├── shared/         UI kit, constants, API client, i18n
│   │   └── proxy.ts        locale routing (next-intl)
│   └── locales/            vi and en message files
├── docs/                   setup guides and design notes
└── AGENTS.md               development workflow
```

## Architecture

**Backend.** Each folder under `app/modules/` is a self-contained module. It owns its constants, config, exceptions, schemas, models, repository, unit of work, services (one use case per file), dependencies and router. Other modules may import only its `public.py`; `lint-imports` and `scripts/check_module_boundaries.py` enforce this. `app/core/` holds shared mechanism only, and `app/integrations/` wraps external systems. Every response uses one envelope with `success`, `data` and `error`, where `error.code` is a stable key the frontend translates.

**Frontend.** Code depends in one direction: `shared → entities → modules → app`. `entities/` holds domain schemas, query keys and read hooks. `modules/` holds feature workflows, mutations and views. `app/` holds routes only. `eslint-plugin-boundaries` enforces the direction, and fetchers validate API responses with Zod.

The full rules are in [`.agents/skills/fastapi-modular-scaffold`](.agents/skills/fastapi-modular-scaffold/) and [`.agents/skills/nextjs-modular-architecture`](.agents/skills/nextjs-modular-architecture/).

## Prerequisites

- Docker with Compose, for the infrastructure services and the backend tests
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20.9+ and [pnpm](https://pnpm.io/)
- A DX Core OAuth client (client ID and secret). SSO is the only way to sign in.

## Local development

The quickest setup runs the infrastructure in Docker and the API and web app on your machine.

### 1. Start the infrastructure

```bash
cd backend
docker compose up -d postgres redis rabbitmq mongo minio
```

| Service | Port |
|---|---|
| PostgreSQL | 5432 |
| Redis | 6379 |
| RabbitMQ | 5672, management UI on 15672 |
| MongoDB | 27017 |
| MinIO | 9000, console on 9001 |

The API connects to RabbitMQ and MongoDB at startup, so it won't boot without them.

### 2. Install and configure the backend

```bash
uv sync
cp .env.example .env
```

`.env.example` is written for an API running inside Compose. When the API runs on your machine, replace the hostnames `postgres`, `redis`, `rabbitmq`, `mongo` and `minio` with `localhost`.

Then fill in the settings for the features you use:

| Setting | Used for |
|---|---|
| `BACKEND_BASE_URL`, `FRONTEND_BASE_URL` | Building the SSO redirect URI and sending the user back to the web app. The frontend URL is also allowed by CORS. |
| `AUTH__JWT_SECRET` | Signing session tokens |
| `DX_CORE__CLIENT_ID`, `DX_CORE__CLIENT_SECRET`, `DX_CORE__SCOPES` | SSO sign-in. Register `<BACKEND_BASE_URL>/api/v1/auth/oauth/dx/callback` as the redirect URI. |
| `DX_CORE__FERNET_KEY` | Encrypting stored DX tokens |
| `USERS__ADMIN_EMAIL` | Optional break-glass admin, created by `seed_admin` |
| `CLOUDFLARE__FERNET_KEY` | Encrypting Cloudflare API tokens |
| `OBSERVABILITY__FERNET_KEY` | Encrypting Loki credentials |
| `OBSERVABILITY__LOKI_WEBHOOK_SECRET` | The bearer token Alertmanager sends to the Loki alert webhook |
| `NOTIFICATIONS__FERNET_KEY` | Encrypting Telegram bot tokens and Base.vn webhook URLs |
| `EMAIL__SMTP_HOST`, `EMAIL__SMTP_PORT`, `EMAIL__SMTP_USERNAME`, `EMAIL__SMTP_PASSWORD`, `EMAIL__SMTP_FROM_ADDRESS` | Email notifications |
| `MONGO__URL` | Audit log database |

Generate a Fernet key with:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`ENV` controls the API docs (`/docs`, `/redoc`, `/openapi.json`):

| `ENV` | API docs |
|---|---|
| `dev` | Open |
| `stg` | Behind HTTP Basic auth, using `DOCS_USERNAME` and `DOCS_PASSWORD` |
| `prod`, the default when unset | Disabled |

### 3. Migrate, seed and run the API

```bash
uv run alembic upgrade head
uv run python -m app.seeds.seed_rbac    # roles and permissions
uv run python -m app.seeds.seed_admin   # break-glass admin; skipped when USERS__ADMIN_EMAIL is unset
uv run uvicorn app.main:app --reload --port 8000
```

Check http://localhost:8000/health. With `ENV=dev`, the API docs are at http://localhost:8000/docs.

Two background processes run separately from the API:

```bash
uv run python -m app.worker      # RabbitMQ consumer; its message handler is still a placeholder
uv run python -m app.scheduler   # drift reconciliation, every OBSERVABILITY__RECONCILIATION_INTERVAL_SECONDS (default 1200)
```

### 4. Run the web app

```bash
cd ../frontend
cp .env.example .env
pnpm install
pnpm dev
```

`NEXT_PUBLIC_API_URL` is the backend base URL without `/api/v1`. The example file already sets it to `http://localhost:8000`.

Open http://localhost:3000 and sign in with DX SSO. If you seeded a break-glass admin, signing in with that email gives you the admin role.

## Running the stack in Docker

`backend/Makefile` wraps Docker Compose. Run `make help` in `backend/` to list the commands.

| Command | What it does |
|---|---|
| `make up` | Build and start the stack. `make up ENV=prod` uses `docker-compose.prod.yml` and `.env.prod`. |
| `make down` | Stop and remove the containers |
| `make migrate` | Run `alembic upgrade head` in the `api` container |
| `make seed` | Run every script in `app/seeds/` in the `api` container, `seed_rbac` first |
| `make logs`, `make worker-logs` | Follow the API or worker logs |

A first run is `make up`, `make migrate`, then `make seed`. The hostnames in `.env.example` already match the Compose services.

Neither Compose file runs the scheduler. `docker-compose.prod.yml` has no MongoDB, so point `MONGO__URL` in `.env.prod` at an existing instance. The production stack publishes the API on port 8001.

## Alert webhooks

Cloudflare and Alertmanager push alerts to the API, so these endpoints must be reachable from those services:

| Endpoint | Sender and check |
|---|---|
| `POST /api/v1/webhooks/cloudflare-alert/{cloudflare_account_id}` | Cloudflare notifications. The `cf-webhook-auth` header must match the secret stored for that account. |
| `POST /api/v1/webhooks/loki-alert` | Alertmanager, with `Authorization: Bearer <OBSERVABILITY__LOKI_WEBHOOK_SECRET>` |

## Tests and checks

Backend, from `backend/`:

```bash
docker compose up -d redis
CACHE__URL=redis://localhost:6379/0 uv run pytest
uv run ruff check app tests
uv run ruff format --check app tests
uv run lint-imports
uv run python scripts/check_module_boundaries.py --strict
```

- Docker must be running. The tests start PostgreSQL and MongoDB in throwaway containers, but they use the real Redis at `CACHE__URL` and flush that Redis database.
- Pass `CACHE__URL` on the command line when your `.env` points at the Compose hostname `redis`.

Frontend, from `frontend/`:

```bash
pnpm lint
pnpm exec tsc --noEmit
pnpm test
pnpm build
```

## Contributing

Read [`AGENTS.md`](AGENTS.md) first. It defines the workflow for people and coding agents alike: read the architecture skills, write a plan, run GitNexus impact analysis before changing a symbol, and review the diff against the skills.

- **Branches:** branch `feature/`, `fix/`, `refactor/` or `chore/` off `develop` and open the pull request into `develop`. Only `hotfix/` branches start from `main`. Never commit straight to `main` or `develop`.
- **Commits:** use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`.
- **Releases:** merging `develop` into `main` is a release. Bump the version in `backend/pyproject.toml` and `frontend/package.json`, tag `vX.Y.Z` and update `CHANGELOG.md`.
- **Code graph:** index the repository with `npx gitnexus analyze` before running impact analysis.

## Documentation

| Document | Contents |
|---|---|
| [docs/cloudflare/setup.md](docs/cloudflare/setup.md) | Creating the Cloudflare API token and choosing its permissions |
| [docs/grafana/setup.md](docs/grafana/setup.md) | Getting a Loki endpoint and configuring it for an environment |
| [docs/tasks/sso-login.md](docs/tasks/sso-login.md) | DX SSO sign-in flow (Vietnamese) |
| [docs/tasks/devops-control-panel-schema.md](docs/tasks/devops-control-panel-schema.md) | Data model design (Vietnamese) |
| [docs/tasks/cloudflare-api-reference.md](docs/tasks/cloudflare-api-reference.md) | Cloudflare endpoints the app calls (Vietnamese) |
| [docs/tasks/grafana-loki-integration.md](docs/tasks/grafana-loki-integration.md) | Loki HTTP API notes (Vietnamese) |
| [docs/tasks/apply_cache.md](docs/tasks/apply_cache.md) | Redis cache-aside design |
| [docs/superpowers/](docs/superpowers/) | Design specs and implementation plans |
