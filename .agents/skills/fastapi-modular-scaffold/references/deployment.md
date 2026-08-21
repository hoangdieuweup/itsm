# Deployment: env files, compose, Makefile, scripts, seeds

## Env file matrix

| File | Used by | Git tracked | Notes |
|---|---|:---:|---|
| `.env.example` | Nobody directly — it's the template | ✅ | Every variable the app reads, with safe/placeholder defaults |
| `.env` | Local dev, `docker-compose.yml` | ❌ | `cp .env.example .env`, then fill in local values |
| `.env.prod` | `docker-compose.prod.yml` | ❌ | `cp .env.example .env.prod`, then give **every** secret a value that differs from `.env` — `JWT_SECRET`-equivalents, DB password, API keys, all of it |

Never commit `.env` or `.env.prod`. Only `.env.example` is tracked, and it must never contain a real credential — placeholders only.

## Two compose files, one Dockerfile

`docker-compose.yml` and `docker-compose.prod.yml` build the same `Dockerfile` and run the same image; they differ in how:
- **Local (`docker-compose.yml`)**: bind-mounts `./app`, `api` runs `uv run uvicorn ... --reload`, `env_file: .env`.
- **Prod (`docker-compose.prod.yml`)**: no bind mount, `api` runs the image's own `CMD` (`scripts/start.sh` → Gunicorn managing Uvicorn workers, no reload), `env_file: .env.prod`, a distinct host port (`8001` by default) so it can run alongside a non-prod stack on the same host, `restart: unless-stopped` on every service, and infra services (`postgres`/`redis`/`rabbitmq`/`minio`) expose **no** host ports at all — only `api`/`worker` need to be reachable from outside the Docker network.

If the queue integration is selected, both compose files also define a `worker` service running the same image with a different command (`app.worker` directly in dev, `scripts/start-worker.sh` in prod) — see "Consumer process" below.

## Makefile

```
make up               # docker compose -f docker-compose.yml up -d --build
make up ENV=prod       # docker compose -f docker-compose.prod.yml up -d --build
make migrate [ENV=prod]
make seed [ENV=prod]   # every app/seeds/seed_*.py, in order, idempotent
make logs [ENV=prod]
make down [ENV=prod]
```
`ENV` selects the compose file (default `stg`, i.e. `docker-compose.yml` — the same file local dev uses; the app's own `ENV` setting inside `.env`/`.env.prod` is what actually switches `dev`/`stg`/`prod` behavior at the application level, per `SKILL.md`'s docs/debug-logging matrix). The Makefile only decides which compose file and env file to point Docker at.

## Startup scripts

- **`scripts/start.sh`** — the API server. `gunicorn` manages `WEB_CONCURRENCY` Uvicorn worker processes (2 by default, 4 when `ENV=prod`, override either with the `WEB_CONCURRENCY` env var). This is what the Dockerfile's `CMD` runs; local dev bypasses it in favor of `--reload` for iteration speed.
- **`scripts/start-worker.sh`** — runs `python -m app.worker`, the queue consumer process (only generated when the `queue` integration is selected).

## Consumer process

`app/worker.py` is a separate process from the API on purpose (see `references/messaging.md`'s "Consumer process" section) — a slow or crashing handler must never be able to starve request handling. It's generated with one consumer task per selected domain module's exchange, each bound with a catch-all routing key; `handle_message` is a placeholder dispatch table to fill in with real use-case calls as the project grows. Split it into one worker process per module later if a single module's consumer needs independent scaling or its own deploy cadence — don't do that up front.

## Seed scripts

`app/seeds/` is a package of standalone, idempotent scripts — one file per concern, run with `python -m app.seeds.<name>`. **Idempotent** means safe to run on every deploy, including production: check whether the data already exists before creating it, and log either outcome. `app/seeds/seed_<first-module>.py` is generated as the concrete pattern to copy — real seed data (an owner account, reference/lookup rows, feature flags) follows the same shape: query for existence, create only if missing, commit, log.

A seed script importing a module's `repository.py` directly (not through `public.py`) is a deliberate, documented exception to the facade rule — seeds are operational tooling in the same category as `migrations/env.py`, which already imports every module's `models.py` directly.

## Deployment checklist

### First deploy
- [ ] `.env` and `.env.prod` created from `.env.example`, every secret filled in and **different between the two**
- [ ] `make up [ENV=prod]`
- [ ] `make migrate [ENV=prod]`
- [ ] `make seed [ENV=prod]`
- [ ] `curl http://localhost:8000/health` (local/stg) or `:8001` (prod, if using the default port split)

### Every update
- [ ] Pull code, review new migration files before running them
- [ ] `make up [ENV=prod]` (rebuilds the image)
- [ ] `make migrate [ENV=prod]` if a migration was added
- [ ] `make seed [ENV=prod]` if a new seed script was added
- [ ] `make logs [ENV=prod]` — confirm the API and worker (if present) started cleanly
