# Shared Backend Mechanics — Design

- **Date:** 2026-09-14
- **Status:** sections 1–3 approved in chat; implementation requested ("làm đi").
- **Scope:** backend (`app/core`, `auth`, `cloudflare`, `notifications`, `observability`, `projects`, `rbac`, `users`), plus four frontend translations.
- **Follow-up:** HTML email notifications with Jinja2 get their own spec.

## Problem

- **Scattered secret handling.** `FernetCodec.encrypt/decrypt` is called in 40 places, each passing its module's key: `cloudflare` 32, `notifications` 3, `observability` 3, `auth` 2. Only `auth` handles a failed decrypt. The other modules answer 500 with a raw `cryptography` exception when a key is wrong or has been rotated.
- **Repeated unit-of-work code.** Seven units of work re-implement `commit`/`rollback`. The four with a cache (`cloudflare`, `projects`, `rbac`, `users`) also repeat the same stale-entity queue, which bumps cache versions after the commit.
- **Repeated pagination code.** 17 of the 19 `list_page` implementations are the same `select … limit/offset` plus a `count`.
- **Repeated credential lookups in `cloudflare`.** 25 services and `public.py` each repeat the same account lookup, token lookup and decrypt.

## Decisions

1. **Where shared code goes.** Placement follows fastapi-modular-scaffold:
   - Mechanism goes in `app/core`.
   - Duplication inside one module stays in that module.
   - `modules/common` only receives business concepts shared by three or more modules. None were found: the only overlap is the severity values in `audit` and `observability`.
2. **Decrypt failures.** `core` raises one error, and each module maps it to its own error code, with translations.
3. **Secret handling (approach A).** Repositories encrypt on write and decrypt on read, so services never touch `FernetCodec` or a key.
   - **Rejected: a SQLAlchemy `TypeDecorator`.** It decrypts on every row load, so one bad key breaks whole lists. Its errors surface inside the ORM, and it makes secrets easy to leak into read schemas.
   - **Rejected: per-module ciphers injected into services.** Services would still fetch and decrypt the ciphertext themselves.

## 1. Secrets and decrypt errors

### Core

- **`app/core/exceptions.py`:** add `SecretUnreadableError(ConflictError)`, with code `secret_unreadable` and status 409.
- **`app/core/crypto.py`:** `FernetCodec.decrypt` maps `InvalidToken` and `ValueError` (wrong or empty key) to `SecretUnreadableError`. The signature does not change; GitNexus rates `FernetCodec` CRITICAL with 33 direct callers. `encrypt` is unchanged, because a bad key at write time is a configuration error.

### Module errors

All of these subclass `SecretUnreadableError` (409) and are raised by the owning repository:

| Module | Error | Code |
|---|---|---|
| `auth` | `DxTokenUnreadable` (existing; base class changes) | `auth_dx_token_unreadable` |
| `cloudflare` | `CloudflareAccountTokenUnreadable` | `cloudflare_account_token_unreadable` |
| `cloudflare` | `CloudflareWebhookSecretUnreadable` | `cloudflare_webhook_secret_unreadable` |
| `observability` | `LokiCredentialUnreadable` | `loki_credential_unreadable` |
| `notifications` | `NotificationChannelSecretUnreadable` | `notification_channel_secret_unreadable` |

### Repository contracts (plaintext in, plaintext out)

| Repository | Change |
|---|---|
| `cloudflare` accounts | `create/update(api_token=<plaintext>)`. `get_token_ciphertext` becomes `get_api_token` (see also `get_credentials`, §3). `get_webhook_destination_ciphertext` becomes `get_webhook_destination` and returns `(destination_id, secret)`. `set_webhook_destination(secret=<plaintext>)`. |
| `observability` Loki configs | `create/update(credential=<plaintext>)`. `get_credential_ciphertext` becomes `get_credential`. `LokiAuthHelper.resolve_loki_auth_header` takes the plaintext credential. |
| `notifications` channels | Already encrypts on write. `get_config_ciphertext_fields` becomes `get_dispatch_config`, which returns the config with its secret field decrypted. |
| `auth` DX tokens | `_decrypt` catches `SecretUnreadableError` instead of `InvalidToken`/`ValueError`. |

Services and `cloudflare/public.py` stop importing `FernetCodec` and the module keys.

### Special paths

- **Cloudflare webhook verification** (`verify_cloudflare_webhook_secret`): an unreadable stored secret is rejected like a wrong secret (`InvalidWebhookSecret`, 401) and logged, because the caller is Cloudflare, not a user.
- **Incident fan-out** (`NotificationsApi.dispatch`): an unreadable channel secret is already caught per channel and recorded as a failed dispatch. The test-send endpoint returns the 409 with its code.

### Frontend

The four new codes go into `common.errors` (en, vi) and ask an admin to re-enter the token or credential. `useApiErrorMessage` falls back to `common.errors`, so the Cloudflare, log viewer and notifications pages all show them.

There are no data or schema changes and no migration.

## 2. Unit of work and pagination

### Unit of work

- **`app/core/base/uow.py`:**
  - `AbstractCachedUnitOfWork(AbstractUnitOfWork)` declares `mark_stale(entity, entity_id)`.
  - `CacheVersionBumper(Protocol)` declares `bump_version(entity, entity_id)`. It exists because import-linter forbids `app.core` from importing `app.integrations.cache`.
- **New `app/core/uow.py`**, next to `core/database.py`:
  - `SqlAlchemyUnitOfWork(AbstractUnitOfWork)` holds the session and implements `commit` and `rollback`, logging `"<ClassName> rolled back"`.
  - `CachedSqlAlchemyUnitOfWork(SqlAlchemyUnitOfWork, AbstractCachedUnitOfWork)` takes a session and a `CacheVersionBumper`. It queues stale entities and bumps them only after the database commit, and it clears the queue on rollback.
- **Module units of work** keep their abstract contract (repository attributes) and their constructor signature. They inherit `commit`/`rollback`/`mark_stale` and only assign repositories. `users` keeps its immediate-bump method.
- **Risk:** GitNexus rates `CloudflareUnitOfWork` CRITICAL (41 direct callers), `ProjectsUnitOfWork` and `ObservabilityUnitOfWork` HIGH. Constructors and attributes are unchanged and only the base class moves, so the full suite covers the change.

### Pagination

- `app/core/pagination.py` gains `PageQuery.fetch_rows(session, model, *, limit, offset, order_by=None) -> tuple[list[row], int]`. It runs the same two queries the repositories run today.
- The 17 plain `list_page` implementations call it and keep their own row-to-schema mapping (`model_validate`, `_load_many`, `_to_read`).
- `incidents` (filtered) and `audit` (MongoDB) keep their own implementations.

## 3. Cloudflare credentials

- `CloudflareAccountRepository.get_credentials(account_id)` returns `CloudflareCredentials(account_id, cf_account_id, api_token)` or `None`.
  - It reads the account through the existing cache-aside `get_by_id` and decrypts the token.
  - It raises `CloudflareAccountTokenUnreadable` when the token can't be decrypted.
- `CloudflareCredentials` is an internal schema that is never returned by the API. `api_token` is declared with `repr=False`.
- The 25 services replace their five-to-eight-line lookup with one call and a `None` check. Each keeps the error it raises today (mostly `CloudflareAccountNotFound` or `CloudflareConfigNotFound`), so HTTP behaviour does not change. `create_account` and `update_account` pass the plaintext token to the repository instead of encrypting it themselves.
- `public.py` uses the same call in `get_ready_client_for_environment`, `get_ready_client_for_account` and `ensure_webhook_destination`.
- **Kept as is:**
  - The tunnel-ownership check, which is a business decision already expressed in `TunnelOwnershipRules`.
  - `_resolve_sibling_environments`, which exists in only two copies.

## 4. Testing and rollout

- **Process:** test-driven, one commit per task, on branch `refactor/shared-backend-mechanics` from `develop`.
- **Core tests:**
  - `FernetCodec.decrypt` maps a wrong key and an empty key to `SecretUnreadableError`.
  - `CachedSqlAlchemyUnitOfWork` bumps only after commit, in queue order, and clears the queue on rollback. This uses a fake session and bumper.
  - `PageQuery.fetch_rows` returns the page and the total against real Postgres.
- **Module tests:**
  - Repository tests round-trip plaintext and raise the module error for an unreadable secret.
  - Service fakes store plaintext and implement `get_credentials` / `get_credential` / `get_dispatch_config`.
  - Existing router tests keep their status codes.
  - The webhook verification test covers the unreadable-secret rejection.
- **Gates:**
  - Backend: ruff check and format, lint-imports 11/11, `check_module_boundaries.py --strict`, OpenAPI still 65 paths, full backend suite.
  - Frontend: eslint, `tsc --noEmit`, vitest.
  - GitNexus: `detect-changes` against `develop`, and `check --cycles`.

## Out of scope

- A helper for `session.add` / `flush` / `refresh`.
- Tunnel-ownership lookups.
- `_resolve_sibling_environments`.
- HTML email notifications, which have a separate spec.
