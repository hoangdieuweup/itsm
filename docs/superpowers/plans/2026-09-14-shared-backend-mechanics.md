# Shared Backend Mechanics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change how secrets, units of work and pagination are shared across modules, with one behaviour change: an unreadable stored secret now answers 409 with a module error code instead of 500. Specifically:
- Repositories own secret encryption, behind one core decrypt error.
- Unit-of-work and pagination mechanics are shared from `app/core`.
- Cloudflare's repeated credential lookup collapses into one repository call.

**Architecture:**
- `FernetCodec.decrypt` raises `SecretUnreadableError`.
- Every repository that stores a secret encrypts on write, decrypts on read, and re-raises its own subclass of that error.
- `app/core/uow.py` provides `SqlAlchemyUnitOfWork` and `CachedSqlAlchemyUnitOfWork`.
- `app/core/pagination.py` provides `PageQuery.fetch_rows`.
- Cloudflare services call `accounts.get_credentials`.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 (async), pydantic 2, cryptography (Fernet), pytest with testcontainers; next-intl JSON locales.

**Spec:** `docs/superpowers/specs/2026-09-14-shared-backend-mechanics-design.md`

## Global Constraints

- **Git:**
  - Work on branch `refactor/shared-backend-mechanics`, created from `develop` at `708c6a3`.
  - Commit locally only, one commit per task.
  - Merging into `develop` needs explicit approval.
- **fastapi-modular-scaffold rules:**
  - Mechanism goes in `app/core`, never a business concept.
  - `app.core` may not import `app.integrations.*` or `app.modules.*` (import-linter contract `root-is-mechanism`).
  - Import order inside a module:
    - constants/config
    - exceptions/schemas/models
    - rules/utils
    - repository/uow
    - services
    - dependencies
    - router
    - public
  - No bare constants or helpers at module level: use classes with `@helper` / `@database` / `@facade`.
  - No `#` comments in code; use docstrings.
- **HTTP behaviour:** existing routes keep their status codes. The only exception is an unreadable stored secret, which answers 409 with a module code.
- **Data:** no database migration and no change to the stored ciphertext format.
- **Secrets in output:**
  - Never print a secret value. Tests use literal tokens such as `"plain"`.
  - `CloudflareCredentials.api_token` is declared with `repr=False`.
  - Filter pytest output so that no settings `repr` is printed.
- **Backend test command:** `CACHE__URL=redis://localhost:6379/0 uv run pytest <path> -q -p no:cacheprovider`. It needs Docker running and `docker compose up -d redis` in `backend/`.
- **Final gates:**
  - `uv run ruff check app tests`
  - `uv run ruff format --check app tests`
  - `uv run lint-imports` (11 kept)
  - `uv run python scripts/check_module_boundaries.py --strict`
  - OpenAPI still 65 paths
  - The full backend suite
  - `pnpm lint`, `pnpm exec tsc --noEmit` and `pnpm test`
  - GitNexus: run `analyze --force`, then restore `AGENTS.md` and `CLAUDE.md`, then run `detect-changes --scope compare --base-ref develop` and `check --cycles`.

## Impact (GitNexus, upstream)

| Symbol | Risk | Mitigation |
|---|---|---|
| `FernetCodec` | CRITICAL (33 direct) | The signature is unchanged. Only the exception raised by `decrypt` changes, and the one catcher (`auth` repository) is updated in the same task. |
| `CloudflareUnitOfWork` | CRITICAL (41 direct) | The constructor and repository attributes are unchanged; only the base class changes. The full suite runs after the task. |
| `ProjectsUnitOfWork`, `ObservabilityUnitOfWork` | HIGH (23 and 20 direct) | Same mitigation as `CloudflareUnitOfWork`. |
| `RbacUnitOfWork`, `UsersUnitOfWork`, `NotificationsUnitOfWork`, `CloudflareAccountRepository`, `CloudflareApi` | MEDIUM | The contract changes are listed per task. Service fakes and facade fakes are updated in the same commit. |
| `AuthUnitOfWork`, `LokiConfigRepository`, `NotificationChannelRepository`, `LokiAuthHelper`, `DispatchNotification`, `verify_cloudflare_webhook_secret`, `DxTokenRepository` | LOW | Covered by the module tests. |

## File Map

| Task | Create | Modify |
|---|---|---|
| 1 | `tests/core/__init__.py`, `tests/core/test_crypto.py` | `app/core/exceptions.py`, `app/core/crypto.py`, `app/modules/auth/exceptions.py`, `app/modules/auth/repository.py` |
| 2 | — | `app/modules/cloudflare/{constants,exceptions,schemas,public}.py`, `repository/accounts.py`, 27 service files, `app/modules/observability/dependencies.py`, `tests/cloudflare/{test_services,test_public,test_repository}.py`, `tests/observability/test_dependencies.py` |
| 3 | — | `app/modules/observability/{constants,exceptions}.py`, `repository/loki_configs.py`, `services/loki/{create_loki_config,update_loki_config,run_log_query,stream_log_tail}.py`, `utils/auth.py`, `tests/observability/{test_services,test_repository,test_router}.py` |
| 4 | — | `app/modules/notifications/{constants,exceptions,repository}.py`, `services/dispatch_notification.py`, `tests/notifications/{test_services,test_repository,test_public}.py` |
| 5 | `app/core/uow.py`, `tests/core/test_uow.py` | `app/core/base/uow.py`, the 7 `app/modules/*/uow.py` files |
| 6 | `tests/core/test_pagination.py` | `app/core/pagination.py`, 16 repository files (17 `list_page`) |
| 7 | — | `frontend/locales/{en,vi}/common.json`, this plan (execution notes) |

---

### Task 1: Core decrypt error

**Files:**
- Create: `backend/tests/core/__init__.py` (empty), `backend/tests/core/test_crypto.py`
- Modify: `backend/app/core/exceptions.py`, `backend/app/core/crypto.py`, `backend/app/modules/auth/exceptions.py`, `backend/app/modules/auth/repository.py`

**Interfaces:**
- Produces: `app.core.exceptions.SecretUnreadableError(ConflictError)`, with `code = "secret_unreadable"` and status 409.
- Produces: `FernetCodec.decrypt(ciphertext: str, *, key: str) -> str`, which raises `SecretUnreadableError`.

- [ ] **Step 1: Write the failing test** `tests/core/test_crypto.py`

```python
"""Unit tests for app.core.crypto."""

import pytest
from cryptography.fernet import Fernet

from app.core.crypto import FernetCodec
from app.core.exceptions import SecretUnreadableError


def _key() -> str:
    return Fernet.generate_key().decode()


class TestFernetCodec:
    def test_round_trips_a_value(self) -> None:
        key = _key()

        assert FernetCodec.decrypt(FernetCodec.encrypt("secret", key=key), key=key) == "secret"

    def test_another_key_raises_secret_unreadable(self) -> None:
        ciphertext = FernetCodec.encrypt("secret", key=_key())

        with pytest.raises(SecretUnreadableError):
            FernetCodec.decrypt(ciphertext, key=_key())

    def test_an_empty_key_raises_secret_unreadable(self) -> None:
        ciphertext = FernetCodec.encrypt("secret", key=_key())

        with pytest.raises(SecretUnreadableError):
            FernetCodec.decrypt(ciphertext, key="")

    def test_a_tampered_ciphertext_raises_secret_unreadable(self) -> None:
        with pytest.raises(SecretUnreadableError):
            FernetCodec.decrypt("not-a-fernet-token", key=_key())
```

- [ ] **Step 2: Run the test and confirm it fails.** Run: `... pytest tests/core/test_crypto.py`. Expected: an `ImportError` because `SecretUnreadableError` does not exist yet.

- [ ] **Step 3: Implement.** Append to `app/core/exceptions.py`:

```python
class SecretUnreadableError(ConflictError):
    """Base for a stored secret that can't be decrypted with the configured key —
    it was saved under a different key, or no valid key is set. The owning module
    subclasses it with its own code so the message says which secret to re-enter."""

    code = "secret_unreadable"
    message = "Stored secret cannot be decrypted with the current key"
```

Replace `app/core/crypto.py` so that `decrypt` maps the failure:

```python
"""Symmetric encryption mechanism for any module storing a secret at rest.

Generic on purpose: no key is hardcoded or read from settings here — each
module that stores a secret (auth, cloudflare, notifications, observability)
supplies its own Fernet key from its own config.py, keeping "core holds
mechanism, never a business concept" intact.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import SecretUnreadableError


class FernetCodec:
    """Encrypt/decrypt a string value with a caller supplied Fernet key."""

    @staticmethod
    def encrypt(plaintext: str, *, key: str) -> str:
        """Return the ciphertext for plaintext, encrypted with key."""
        return Fernet(key.encode()).encrypt(plaintext.encode()).decode()

    @staticmethod
    def decrypt(ciphertext: str, *, key: str) -> str:
        """Return the plaintext for ciphertext, decrypted with key. Raises
        SecretUnreadableError when the ciphertext was tampered with, was encrypted
        under another key, or key is not a valid Fernet key."""
        try:
            return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
        except (InvalidToken, ValueError) as exc:
            raise SecretUnreadableError() from exc
```

In `app/modules/auth/exceptions.py`:
- Import `SecretUnreadableError` instead of `AppError`.
- Declare `class DxTokenUnreadable(SecretUnreadableError)`.
- Remove its `status_code = 500` line, so it inherits 409.
- Keep `code = ErrorCode.DX_TOKEN_UNREADABLE` and its message.

In `app/modules/auth/repository.py`, drop the `from cryptography.fernet import InvalidToken` import, and make `_decrypt` catch the core error:

```python
    @helper
    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt one token value with the auth module's DX token key, raising
        DxTokenUnreadable when it was encrypted under another key or no valid key is set."""
        try:
            return FernetCodec.decrypt(ciphertext, key=auth_settings.DX_TOKEN_FERNET_KEY.get_secret_value())
        except SecretUnreadableError as exc:
            raise DxTokenUnreadable() from exc
```

- [ ] **Step 4: Run.** Run: `... pytest tests/core tests/auth`. Expected: everything passes, including the existing `test_reports_unreadable_tokens_when_the_key_changed`.

- [ ] **Step 5: Commit.** Run `ruff check --fix --select I` and `ruff format`, then `detect-changes --scope staged`, then commit `feat(core): raise SecretUnreadableError when a stored secret can't be decrypted`.

---

### Task 2: Cloudflare keeps account secrets in its repository

**Files:** see the File Map. The 27 service files are listed in Step 5.

**Interfaces:**
- Consumes: `SecretUnreadableError` and `FernetCodec` (Task 1).
- Produces (`app/modules/cloudflare`):
  - `ErrorCode.ACCOUNT_TOKEN_UNREADABLE = "cloudflare_account_token_unreadable"` and `ErrorCode.WEBHOOK_SECRET_UNREADABLE = "cloudflare_webhook_secret_unreadable"`.
  - `CloudflareAccountTokenUnreadable(SecretUnreadableError)` and `CloudflareWebhookSecretUnreadable(SecretUnreadableError)`.
  - The schema:

    ```python
    class CloudflareCredentials(FrozenModel):
        account_id: UUID
        cf_account_id: str
        api_token: str = Field(repr=False)
    ```

  - `AbstractCloudflareAccountRepository` changes:
    - `create(*, label, cf_account_id, api_token, created_by)`: `api_token` is plaintext.
    - `update(account_id, *, label, api_token)`: `api_token` is plaintext or `None`.
    - `get_credentials(account_id) -> CloudflareCredentials | None` (replaces `get_token_ciphertext`).
    - `get_webhook_destination_id(account_id) -> str | None`.
    - `get_webhook_secret(account_id) -> str | None` (decrypted).
    - `set_webhook_destination(account_id, *, cf_webhook_destination_id: str, secret: str)`.
    - `get_webhook_destination_ciphertext` is removed.
  - `cloudflare.public` exports `CloudflareWebhookSecretUnreadable`.

- [ ] **Step 1: Write the failing tests.**

In `tests/cloudflare/test_repository.py`, reuse the file's `_session` fixture and the way its existing tests build accounts:
- A test that sets `cloudflare_settings.FERNET_KEY` to a generated key with monkeypatch, then checks:
  - `create(api_token="plain")` stores a value that is not `"plain"` in the `api_token` column.
  - `get_credentials(id)` returns `api_token == "plain"` and the row's `cf_account_id`.
- A test that switches the key after `create`: `get_credentials` raises `CloudflareAccountTokenUnreadable`.
- A test that `get_credentials(uuid4())` returns `None`.
- A test that `set_webhook_destination(id, cf_webhook_destination_id="wh", secret="s")` round-trips: `get_webhook_destination_id` returns `"wh"` and `get_webhook_secret` returns `"s"`. After a key switch, `get_webhook_secret` raises `CloudflareWebhookSecretUnreadable` while `get_webhook_destination_id` still returns `"wh"`.

In `tests/observability/test_dependencies.py`, add:

```python
class RaisingCloudflareApiForWebhook:
    async def get_webhook_secret(self, account_id):
        raise CloudflareWebhookSecretUnreadable()


class TestVerifyCloudflareWebhookSecretUnreadable:
    async def test_unreadable_stored_secret_rejects(self) -> None:
        with pytest.raises(InvalidWebhookSecret):
            await verify_cloudflare_webhook_secret(
                cloudflare_account_id=uuid4(),
                cf_webhook_auth="anything",
                cloudflare_api=RaisingCloudflareApiForWebhook(),
            )
```

- [ ] **Step 2: Run and confirm the failure.** Expected: an `ImportError` or `AttributeError` for the new names.

- [ ] **Step 3: Errors and schema.**
  - Add the two `ErrorCode` members and the two exception classes. The exceptions module imports `SecretUnreadableError` from `app.core.exceptions`.
  - In `schemas.py`, import `Field` from pydantic and add `CloudflareCredentials`, with the docstring: "An account's Cloudflare id plus its decrypted API token, for calling the Cloudflare API. Internal only — never returned by a route; api_token stays out of repr."

- [ ] **Step 4: Repository.**
  - Update the abstract docstrings to say secrets are plaintext in and out.
  - Remove `get_token_ciphertext` and `get_webhook_destination_ciphertext`, and add the new abstract methods.
  - Concrete class, `create`: `api_token=self._encrypt(api_token)`.
  - Concrete class, `update`: `if api_token is not None: row.api_token = self._encrypt(api_token)`.
  - Concrete class, new methods:

```python
    @database
    async def get_credentials(self, account_id: UUID) -> CloudflareCredentials | None:
        """Return the account's Cloudflare id and decrypted API token, or None when the
        account doesn't exist. Read straight from the row, so the token never enters the cache."""
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None:
            return None
        return CloudflareCredentials(
            account_id=row.id,
            cf_account_id=row.cf_account_id,
            api_token=self._decrypt(row.api_token, CloudflareAccountTokenUnreadable),
        )

    @database
    async def get_webhook_destination_id(self, account_id: UUID) -> str | None:
        """Return the registered cf_webhook_destination_id, or None. Never decrypts."""
        row = await self._session.get(CloudflareAccount, account_id)
        return row.cf_webhook_destination_id if row is not None else None

    @database
    async def get_webhook_secret(self, account_id: UUID) -> str | None:
        """Return the decrypted webhook secret, or None when no destination was registered."""
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None or row.webhook_secret_ciphertext is None:
            return None
        return self._decrypt(row.webhook_secret_ciphertext, CloudflareWebhookSecretUnreadable)

    @database
    async def set_webhook_destination(
        self, account_id: UUID, *, cf_webhook_destination_id: str, secret: str
    ) -> None:
        """Persist a newly registered webhook destination, encrypting its secret."""
        row = await self._session.get(CloudflareAccount, account_id)
        if row is None:
            raise CloudflareAccountNotFound()
        row.cf_webhook_destination_id = cf_webhook_destination_id
        row.webhook_secret_ciphertext = self._encrypt(secret)
        await self._session.flush()

    @helper
    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a secret with the cloudflare module's key."""
        return FernetCodec.encrypt(plaintext, key=cloudflare_settings.FERNET_KEY)

    @helper
    def _decrypt(self, ciphertext: str, unreadable: type[SecretUnreadableError]) -> str:
        """Decrypt a secret with the cloudflare module's key, raising `unreadable` when it can't be."""
        try:
            return FernetCodec.decrypt(ciphertext, key=cloudflare_settings.FERNET_KEY)
        except SecretUnreadableError as exc:
            raise unreadable() from exc
```

- [ ] **Step 5: Services.** Run the migration script below from `backend/`, save it as `scratchpad/migrate_cloudflare_credentials.py`, then hand-edit the two encrypting services.

The script handles three shapes:
- **Token, then account:** `create_tunnel`, `delete_tunnel`, `refresh_tunnel_status`, `reveal_tunnel_token`, `sync_tunnels`, and `add/remove/update_tunnel_hostname`.
- **Account, then token:** `list_zones`, `reveal_token`, `test_connection`, `create/update_config`, `get_traffic_stats`, `create/delete/list/update_account_dns_record`, and `create/delete/list_account_tunnel(s)`.
- **Token only:** `create/delete/update_dns_record` and `sync_dns_records`.

```python
"""Replace cloudflare services' token lookup + decrypt with accounts.get_credentials."""

import pathlib
import re

ROOT = pathlib.Path("app/modules/cloudflare/services")
FAIL = r"(?:raise \w+\(\)|return await [^\n]+)"
TOKEN = (
    r"(?P<i>[ ]+)(?P<tok>\w+) = await self\._uow\.accounts\.get_token_ciphertext\((?P<id>[\w.]+)\)\n"
    r"(?P=i)if (?P=tok) is None:\n"
    rf"(?P=i)    (?P<fail>{FAIL})\n"
    r"(?P=i)(?P<plain>\w+) = FernetCodec\.decrypt\((?P=tok), key=cloudflare_settings\.FERNET_KEY\)\n"
)
ACCOUNT_AFTER = (
    r"\n?(?P=i)account = await self\._uow\.accounts\.get_by_id\((?P=id)\)\n"
    r"(?P=i)if account is None:\n"
    rf"(?P=i)    {FAIL}\n"
)
ACCOUNT_BEFORE = (
    r"(?P<i>[ ]+)account = await self\._uow\.accounts\.get_by_id\((?P<id>[\w.]+)\)\n"
    r"(?P=i)if account is None:\n"
    rf"(?P=i)    (?P<fail>{FAIL})\n"
    r"(?P=i)(?P<tok>\w+) = await self\._uow\.accounts\.get_token_ciphertext\((?P=id)\)\n"
    r"(?P=i)if (?P=tok) is None:\n"
    rf"(?P=i)    {FAIL}\n"
    r"(?P=i)(?P<plain>\w+) = FernetCodec\.decrypt\((?P=tok), key=cloudflare_settings\.FERNET_KEY\)\n"
)
PATTERNS = [re.compile(TOKEN + ACCOUNT_AFTER), re.compile(ACCOUNT_BEFORE), re.compile(TOKEN)]

changed, manual = [], []
for path in sorted(ROOT.rglob("*.py")):
    text = path.read_text()
    if "get_token_ciphertext" not in text:
        continue
    match = next((m for p in PATTERNS if (m := p.search(text))), None)
    if match is None:
        manual.append(str(path))
        continue
    indent = match.group("i")
    block = (
        f"{indent}credentials = await self._uow.accounts.get_credentials({match.group('id')})\n"
        f"{indent}if credentials is None:\n"
        f"{indent}    {match.group('fail')}\n"
    )
    tail = re.sub(rf"\b{match.group('plain')}\b", "credentials.api_token", text[match.end():])
    tail = tail.replace("account.cf_account_id", "credentials.cf_account_id")
    path.write_text(text[: match.start()] + block + tail)
    changed.append(str(path))
    if re.search(r"\baccount\b\.", tail):
        manual.append(f"{path} (still uses account.<field>)")
print("changed:", len(changed))
print("manual look:", manual)
```

Expected output: `changed: 25`. Review every entry the script puts under `manual look:`. Where a service reads account fields other than `cf_account_id`, restore a single `account = await self._uow.accounts.get_by_id(...)` call.

Then edit the two encrypting services by hand:
- `create_account.py`: delete `ciphertext = FernetCodec.encrypt(...)` and pass `api_token=api_token` to `create`.
- `update_account.py`: delete the `ciphertext` variable and pass `api_token=api_token` to `update`.

Finally, `ruff check --fix --select F401,I` removes the now-unused `FernetCodec` and `cloudflare_settings` imports. Confirm nothing is left:

```bash
grep -rnE "get_token_ciphertext|FernetCodec|cloudflare_settings" app/modules/cloudflare/services
```

Expected: no matches.

- [ ] **Step 6: The facade and the webhook dependency.**

In `public.py`:
- `get_ready_client_for_environment`: after resolving the config, call `get_credentials(config.cloudflare_account_id)`, return `None` if it is `None`, and build `ReadyCloudflareClient(client=self._client, cf_account_id=credentials.cf_account_id, api_token=credentials.api_token, cloudflare_account_id=credentials.account_id, zone_id=config.zone_id)`.
- `get_ready_client_for_account`: same, without `zone_id`.
- `ensure_webhook_destination`:
  - `existing_id = await self._uow.accounts.get_webhook_destination_id(...)`; return it when set.
  - Otherwise `credentials = await self._uow.accounts.get_credentials(...)`, raising `CloudflareAccountNotFound` when it is `None`.
  - Create the destination with `credentials`, then `set_webhook_destination(..., secret=secret)`, then commit.
- `get_webhook_secret`: `return await self._uow.accounts.get_webhook_secret(cloudflare_account_id)`, and mention the raised error in the docstring.
- Drop the `FernetCodec` and `cloudflare_settings` imports, and add `CloudflareWebhookSecretUnreadable` to the imports and to `__all__`.

In `observability/dependencies.py`, `verify_cloudflare_webhook_secret` wraps the lookup (add `logging`/`logger` if the file lacks them):

```python
    try:
        stored_secret = await cloudflare_api.get_webhook_secret(cloudflare_account_id)
    except CloudflareWebhookSecretUnreadable:
        logger.warning("stored cloudflare webhook secret unreadable account_id=%s", cloudflare_account_id)
        raise InvalidWebhookSecret() from None
```

- [ ] **Step 7: Test fakes.**

`tests/cloudflare/test_services.py`, `FakeCloudflareAccountRepository`:
- Rename `_ciphertexts` to `_tokens`, storing plaintext.
- Remove the two ciphertext getters.
- Add:

```python
    async def get_credentials(self, account_id: UUID) -> CloudflareCredentials | None:
        account = self._rows.get(account_id)
        if account is None or account_id not in self._tokens:
            return None
        return CloudflareCredentials(
            account_id=account.id, cf_account_id=account.cf_account_id, api_token=self._tokens[account_id]
        )

    async def get_webhook_destination_id(self, account_id: UUID) -> str | None:
        return self._webhook_destinations.get(account_id, (None, None))[0]

    async def get_webhook_secret(self, account_id: UUID) -> str | None:
        return self._webhook_destinations.get(account_id, (None, None))[1]

    async def set_webhook_destination(self, account_id: UUID, *, cf_webhook_destination_id: str, secret: str) -> None:
        self._webhook_destinations[account_id] = (cf_webhook_destination_id, secret)
```

Replace every `FernetCodec.encrypt("<literal>", key=TEST_FERNET_KEY)` with the literal, using `re.sub(r'FernetCodec\.encrypt\(("[^"]*"), key=TEST_FERNET_KEY\)', r'\1', text)`, and inline the `ciphertext = FernetCodec.encrypt(...)` variables. The three assertions that read `get_token_ciphertext` become:
- `(await uow.accounts.get_credentials(account.id)).api_token == "<expected plaintext>"`.
- For the unchanged-on-failure test: the original literal.

Remove the `TEST_FERNET_KEY` constant, its fixture and the `FernetCodec` import once they are unused.

Add one test: `ListZones` against a fake whose `get_credentials` raises `CloudflareAccountTokenUnreadable` propagates that error.

`tests/cloudflare/test_public.py`, `FakeAccountsRepo`:
- Constructor `(accounts=None, tokens=None)`, storing plaintext tokens.
- `get_credentials` builds `CloudflareCredentials(account_id=account.id, cf_account_id=account.cf_account_id, api_token=token)`, or returns `None` when either the account or the token is missing.
- Add `get_webhook_destination_id` and `get_webhook_secret` over `_webhook_destinations`, and `set_webhook_destination(..., secret)`.
- Replace `FernetCodec.encrypt("real-token", key=TEST_KEY)` and the secret ciphertext with the plaintext literals.
- Remove the key fixture and the `FernetCodec` import.

In `tests/cloudflare/test_repository.py`, change the not-found webhook test to `secret="c"`.

- [ ] **Step 8: Run.** Run: `... pytest tests/cloudflare tests/observability/test_dependencies.py`. Expected: everything passes.

- [ ] **Step 9: Commit.** Run ruff, then `detect-changes --scope staged`, then commit `refactor(cloudflare): keep account secrets in the repository behind get_credentials`.

---

### Task 3: Observability keeps the Loki credential in its repository

**Interfaces:**
- Consumes: `SecretUnreadableError` and `FernetCodec`.
- Produces:
  - `ErrorCode.CREDENTIAL_UNREADABLE = "loki_credential_unreadable"` and `LokiCredentialUnreadable(SecretUnreadableError)`.
  - `AbstractLokiConfigRepository.get_credential(environment_id) -> str | None` (decrypted; replaces `get_credential_ciphertext`).
  - `create(..., credential: str | None)`: plaintext.
  - `update_by_environment_id(..., credential: str | None, keep_credential: bool = False)`: when `keep_credential` is true, the stored credential column is left untouched.
  - `LokiAuthHelper.resolve_loki_auth_header(config: LokiConfigRead, credential: str | None) -> str | None`: plaintext.

- [ ] **Step 1: Write the failing tests.** In `tests/observability/test_repository.py`:
  - Replace `test_get_credential_ciphertext_returns_raw_column` with `test_get_credential_decrypts_the_stored_value`. With a monkeypatched `observability_settings.FERNET_KEY`, create with `credential="tok"`; the raw row column is not `"tok"`, and `get_credential` returns `"tok"`.
  - Add `test_get_credential_raises_unreadable_after_a_key_change`.
  - Add `test_update_with_keep_credential_leaves_the_column_untouched`: the raw column is equal before and after.

- [ ] **Step 2: Run and confirm the failure.**

- [ ] **Step 3: Implement.**
  - Add the error code and the exception.
  - Repository:
    - `create` stores `self._encrypt(credential) if credential is not None else None`.
    - `update_by_environment_id` does `if not keep_credential: row.credential = self._encrypt(credential) if credential is not None else None`.
    - `get_credential` reads the row and returns `None` when there is no row or no credential; otherwise it returns `self._decrypt(row.credential)`, which raises `LokiCredentialUnreadable`.
    - `_encrypt` / `_decrypt` are `@helper` methods using `observability_settings.FERNET_KEY`, following the cloudflare pattern.
  - `create_loki_config`: `stored_credential = credential if auth_type != LokiAuthType.NONE else None`, and pass `credential=stored_credential`.
  - `update_loki_config`:

```python
        new_auth_type = auth_type if auth_type is not None else existing.auth_type
        keep_credential = new_auth_type != LokiAuthType.NONE and credential is None
        config = await self._uow.loki_configs.update_by_environment_id(
            environment_id,
            ...,
            auth_type=new_auth_type,
            credential=None if new_auth_type == LokiAuthType.NONE else credential,
            keep_credential=keep_credential,
            ...,
        )
```

  - `run_log_query` and `stream_log_tail`: `credential = await self._uow.loki_configs.get_credential(environment_id)`, then `LokiAuthHelper.resolve_loki_auth_header(config, credential)`.
  - `utils/auth.py`:
    - Drop `FernetCodec` and `observability_settings`.
    - Rename the parameter to `credential`.
    - Build `Bearer {credential}` or `Basic base64(credential)`, and return `None` when `credential is None`.
  - Remove the `FernetCodec` imports from the two services.

- [ ] **Step 4: Update the fakes and tests in `tests/observability/test_services.py`.**
  - Fake Loki repository: `_ciphertexts` becomes `_credentials` (plaintext), `get_credential_ciphertext` becomes `get_credential`, and `update_by_environment_id` accepts `keep_credential` and skips writing `_credentials` when it is true.
  - Replace `FernetCodec.encrypt("<literal>", key=TEST_FERNET_KEY)` with the literal.
  - `FernetCodec.decrypt(stored_ciphertext, key=TEST_FERNET_KEY) == "x"` becomes `uow.loki_configs._credentials[env_id] == "x"`.
  - The `LokiAuthHelper` tests pass plaintext.
  - Remove `TEST_FERNET_KEY` and its fixture once they are unused.
  - In `tests/observability/test_router.py`, keep the key fixture, because the real repository encrypts. Replace direct `FernetCodec` usage with the plaintext flow, or keep it where the test asserts on the raw database column.

- [ ] **Step 5: Run.** Run: `... pytest tests/observability`. Expected: everything passes.

- [ ] **Step 6: Commit** `refactor(observability): keep the Loki credential in its repository`.

---

### Task 4: Notifications decrypts channel secrets in its repository

**Interfaces:**
- Produces:
  - `ErrorCode.SECRET_UNREADABLE = "notification_channel_secret_unreadable"` and `NotificationChannelSecretUnreadable(SecretUnreadableError)`.
  - `AbstractNotificationChannelRepository.get_dispatch_config(channel_id) -> dict`, which returns the stored config with the type's secret field decrypted, or `{}` when the channel is missing. It replaces `get_config_ciphertext_fields`.

- [ ] **Step 1: Write the failing tests.** In `tests/notifications/test_repository.py`:
  - Rename `test_get_config_ciphertext_fields_returns_raw_secrets` to `test_get_dispatch_config_decrypts_the_secret`, asserting `fields["bot_token"] == "raw-token"` and `fields["chat_id"] == "1"`.
  - Add `test_get_dispatch_config_raises_unreadable_after_a_key_change`.
  - Change the update test at line 167 to use `get_dispatch_config`, asserting `== "new-token"`.
  - Keep the raw-row encryption assertions, which use `FernetCodec` on the database column.

- [ ] **Step 2: Run and confirm the failure.**

- [ ] **Step 3: Implement.**
  - Add the error code and the exception.
  - Repository: add a `@helper _decrypt_config(channel_type, config) -> dict` that mirrors `_encrypt_config`. When the secret field is present, it decrypts it and maps `SecretUnreadableError` to `NotificationChannelSecretUnreadable`.
  - `get_dispatch_config` returns `self._decrypt_config(row.type, row.config)`, or `{}`.
  - `dispatch_notification.py`: `config = await self._uow.channels.get_dispatch_config(channel.id)`, then `bot_token=config["bot_token"]` and `webhook_url = config["webhook_url"]`. Drop the `FernetCodec` and `notifications_settings` imports.

- [ ] **Step 4: Update the fakes.**
  - `tests/notifications/test_services.py`: the fake stores the plaintext config and exposes `get_dispatch_config`. Remove the encrypt lines and the key fixture if they become unused.
  - `tests/notifications/test_public.py`: rename the fake method.

- [ ] **Step 5: Run.** Run: `... pytest tests/notifications`. Expected: everything passes.

- [ ] **Step 6: Commit** `refactor(notifications): decrypt channel secrets in the repository`.

---

### Task 5: Shared unit of work

**Interfaces:**
- Produces, in `app/core/base/uow.py`:
  - `CacheVersionBumper(Protocol)`, with `async def bump_version(self, entity: str, entity_id: UUID | int | str) -> None`.
  - `AbstractCachedUnitOfWork(AbstractUnitOfWork)`, with abstract `mark_stale(entity: str, entity_id: UUID | int | str) -> None`.
- Produces, in `app/core/uow.py`: `SqlAlchemyUnitOfWork(session)` and `CachedSqlAlchemyUnitOfWork(session, cache)`.

- [ ] **Step 1: Write the failing test** `tests/core/test_uow.py`

```python
"""Unit tests for app.core.uow — fake session and cache, no database."""

from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.uow import CachedSqlAlchemyUnitOfWork, SqlAlchemyUnitOfWork


class RecordingSession:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def commit(self) -> None:
        self._log.append("commit")

    async def rollback(self) -> None:
        self._log.append("rollback")


class RecordingBumper:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def bump_version(self, entity: str, entity_id) -> None:
        self._log.append(f"bump:{entity}:{entity_id}")


def _cached(log: list[str]) -> CachedSqlAlchemyUnitOfWork:
    return CachedSqlAlchemyUnitOfWork(cast(AsyncSession, RecordingSession(log)), RecordingBumper(log))


class TestSqlAlchemyUnitOfWork:
    async def test_commit_and_rollback_delegate_to_the_session(self) -> None:
        log: list[str] = []
        uow = SqlAlchemyUnitOfWork(cast(AsyncSession, RecordingSession(log)))

        await uow.commit()
        await uow.rollback()

        assert log == ["commit", "rollback"]


class TestCachedSqlAlchemyUnitOfWork:
    async def test_bumps_queued_entities_after_the_commit_in_order(self) -> None:
        log: list[str] = []
        uow = _cached(log)
        first, second = uuid4(), uuid4()
        uow.mark_stale("project", first)
        uow.mark_stale("environment", second)

        await uow.commit()

        assert log == ["commit", f"bump:project:{first}", f"bump:environment:{second}"]

    async def test_a_second_commit_does_not_bump_again(self) -> None:
        log: list[str] = []
        uow = _cached(log)
        uow.mark_stale("project", 1)
        await uow.commit()

        await uow.commit()

        assert log == ["commit", "bump:project:1", "commit"]

    async def test_rollback_drops_the_queue_without_bumping(self) -> None:
        log: list[str] = []
        uow = _cached(log)
        uow.mark_stale("project", 1)

        await uow.rollback()
        await uow.commit()

        assert log == ["rollback", "commit"]
```

- [ ] **Step 2: Run and confirm the failure** (`ModuleNotFoundError: app.core.uow`).

- [ ] **Step 3: Implement the core pieces.**

Append to `app/core/base/uow.py`, importing `Protocol` from `typing` and `UUID`:

```python
class CacheVersionBumper(Protocol):
    """What a cached unit of work needs from the cache: bump one entity's version.
    Declared here because app.core may not import app.integrations.cache."""

    async def bump_version(self, entity: str, entity_id: UUID | int | str) -> None:
        """Invalidate every cached read of one entity."""
        ...


class AbstractCachedUnitOfWork(AbstractUnitOfWork):
    """A unit of work whose repositories serve cache-aside reads."""

    @abstractmethod
    def mark_stale(self, entity: str, entity_id: UUID | int | str) -> None:
        """Queue a cache entity for invalidation once THIS uow's own commit() runs."""
        raise NotImplementedError
```

Create `app/core/uow.py`:

```python
"""SQLAlchemy-backed unit of work mechanism every module's concrete unit of work extends."""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database
from app.core.base.uow import AbstractCachedUnitOfWork, AbstractUnitOfWork, CacheVersionBumper

logger = logging.getLogger(__name__)


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """Commits and rolls back one request-scoped AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def commit(self) -> None:
        """Commit the transaction."""
        await self._session.commit()

    @database
    async def rollback(self) -> None:
        """Roll back the transaction."""
        await self._session.rollback()
        logger.warning("%s rolled back", type(self).__name__)


class CachedSqlAlchemyUnitOfWork(SqlAlchemyUnitOfWork, AbstractCachedUnitOfWork):
    """Adds the stale-entity queue. Cache versions are bumped strictly after the
    database commit — bumping first would let a concurrent reader repopulate the
    cache from the pre-commit row (references/caching.md#order-of-operations) —
    and the queue is dropped on rollback."""

    def __init__(self, session: AsyncSession, cache: CacheVersionBumper) -> None:
        super().__init__(session)
        self._cache = cache
        self._stale: list[tuple[str, UUID | int | str]] = []

    def mark_stale(self, entity: str, entity_id: UUID | int | str) -> None:
        """Queue a cache entity for invalidation once this transaction commits."""
        self._stale.append((entity, entity_id))

    @database
    async def commit(self) -> None:
        """Commit the transaction, then invalidate every queued cache entity."""
        await self._session.commit()
        for entity, entity_id in self._stale:
            await self._cache.bump_version(entity, entity_id)
        self._stale.clear()

    @database
    async def rollback(self) -> None:
        """Drop any queued invalidation and roll back the transaction."""
        self._stale.clear()
        await super().rollback()
```

- [ ] **Step 4: Migrate the seven units of work.** Keep each module's docstring, abstract repository attributes and constructor signature.

`cloudflare`, `projects`, `rbac` and `users` (cached):
- The abstract class extends `AbstractCachedUnitOfWork` and drops its own `mark_stale` abstract method. `users` keeps its abstract `invalidate_now`.
- The concrete class is `class <Module>UnitOfWork(Abstract<Module>UnitOfWork, CachedSqlAlchemyUnitOfWork)`.
- Its `__init__(self, session: AsyncSession, cache: CacheClient)` starts with `super().__init__(session, cache)` and then keeps only the repository assignments.
- Delete `self._session`, `self._cache`, `self._stale`, `mark_stale`, `commit`, `rollback` and the module `logger` when it becomes unused.
- `users` keeps `invalidate_now`, which calls `self._cache.bump_version`.

`auth`, `notifications` and `observability` (no cache):
- The concrete class is `class <Module>UnitOfWork(Abstract<Module>UnitOfWork, SqlAlchemyUnitOfWork)`.
- Its `__init__` starts with `super().__init__(session)`, then keeps the repository assignments.
- Delete `commit`, `rollback` and the unused `logger`.

Repository assignments to keep, verbatim:

| Module | Assignments |
|---|---|
| `cloudflare` | `accounts = CloudflareAccountRepository(session, cache)`, `account_managers = CloudflareAccountManagerRepository(session)`, `configs = CloudflareConfigRepository(session)`, `dns_records = DnsRecordRepository(session)`, `tunnels = CloudflareTunnelRepository(session)`, `tunnel_hostnames = TunnelHostnameRepository(session)` |
| `projects` | `projects = ProjectRepository(session, cache)`, `environments = EnvironmentRepository(session, cache)`, `project_links = ProjectLinkRepository(session)`, `project_members = ProjectMemberRepository(session)`, `project_roles = ProjectRoleRepository(session)` |
| `rbac` | `roles = RoleRepository(session, cache)`, `permissions = PermissionRepository(session)`, `user_roles = UserRoleRepository(session, cache)` |
| `users` | `users = UserRepository(session, cache)` |
| `auth` | `dx_tokens = DxTokenRepository(session)` |
| `notifications` | `channels = NotificationChannelRepository(session)` |
| `observability` | `loki_configs = LokiConfigRepository(session)`, `alert_rules = AlertRuleRepository(session)`, `incidents = IncidentRepository(session)` |

- [ ] **Step 5: Run.** Run `... pytest tests/core`, then the full backend suite, `uv run lint-imports`, and `uv run python -c "from app.main import app; print(len(app.openapi()['paths']))"`. Expected: everything passes, 11 contracts kept, 65 paths.

- [ ] **Step 6: Commit** `refactor(core): share unit of work commit, rollback and cache invalidation`.

---

### Task 6: Shared list_page query

**Interfaces:**
- Produces: `PageQuery.fetch_rows(session: AsyncSession, model: type[Any], *, limit: int, offset: int, order_by: Any = None, options: Sequence[Any] = ()) -> tuple[list[Any], int]`, in `app/core/pagination.py`.

- [ ] **Step 1: Write the failing test** `tests/core/test_pagination.py`

```python
"""Integration test for PageQuery against real Postgres, using the users table."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.pagination import PageQuery
from app.modules.common.constants import UserStatus
from app.modules.users.models import User


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


class TestPageQuery:
    async def test_returns_one_ordered_page_and_the_table_total(self, _session: AsyncSession) -> None:
        baseline = await _session.scalar(select(func.count()).select_from(User)) or 0
        emails = sorted(f"page-{uuid4()}@example.com" for _ in range(3))
        _session.add_all(User(email=email, name="Page", status=UserStatus.ACTIVE) for email in emails)
        await _session.flush()

        rows, total = await PageQuery.fetch_rows(
            _session, User, limit=2, offset=0, order_by=User.email.desc()
        )

        assert total == baseline + 3
        assert len(rows) == 2
        assert [row.email for row in rows] == sorted((row.email for row in rows), reverse=True)
```

- [ ] **Step 2: Run and confirm the failure** (`ImportError: PageQuery`).

- [ ] **Step 3: Implement.** Append to `app/core/pagination.py`, adding the imports `from collections.abc import Sequence`, `from typing import Any`, `from sqlalchemy import func, select`, `from sqlalchemy.ext.asyncio import AsyncSession` and `from app.core.base.markers import helper`:

```python
class PageQuery:
    """Runs the two queries behind a repository's list_page."""

    @staticmethod
    @helper
    async def fetch_rows(
        session: AsyncSession,
        model: type[Any],
        *,
        limit: int,
        offset: int,
        order_by: Any = None,
        options: Sequence[Any] = (),
    ) -> tuple[list[Any], int]:
        """Return one page of `model` rows and the table's total row count."""
        stmt = select(model).options(*options).limit(limit).offset(offset)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        rows = list(await session.scalars(stmt))
        total = await session.scalar(select(func.count()).select_from(model))
        return rows, total or 0
```

- [ ] **Step 4: Migrate the 17 `list_page` bodies.** Run `scratchpad/migrate_list_page.py` below from `backend/`. Expected output: `replaced 17 in 16 files`.

```python
"""Replace the plain select/limit/offset + count list_page body with PageQuery.fetch_rows."""

import pathlib
import re

PATTERN = re.compile(
    r"(?P<i>[ ]+)rows = (?P<wrap>list\(\s*)?await self\._session\.scalars\(\s*"
    r"select\((?P<model>\w+)\)(?:\.options\((?P<options>[^\n]*?)\))?"
    r"(?:\.order_by\((?P<order>[\w.]+)\))?\.limit\(limit\)\.offset\(offset\)\s*\)(?(wrap)\s*\))\n"
    r"(?P=i)items = (?P<items>[^\n]+)\n"
    r"(?P=i)total = await self\._session\.scalar\(select\(func\.count\(\)\)\.select_from\((?P=model)\)\)\n"
    r"(?P=i)return items, total or 0\n"
)
IMPORT = "from app.core.pagination import PageQuery\n"

count = 0
files = 0
for path in sorted(pathlib.Path("app/modules").rglob("*.py")):
    text = path.read_text()
    new, n = PATTERN.subn(
        lambda m: (
            f"{m['i']}rows, total = await PageQuery.fetch_rows(\n"
            f"{m['i']}    self._session,\n"
            f"{m['i']}    {m['model']},\n"
            f"{m['i']}    limit=limit,\n"
            f"{m['i']}    offset=offset,\n"
            + (f"{m['i']}    order_by={m['order']},\n" if m["order"] else "")
            + (f"{m['i']}    options=[{m['options']}],\n" if m["options"] else "")
            + f"{m['i']})\n"
            f"{m['i']}return {m['items']}, total\n"
        ),
        text,
    )
    if n:
        if IMPORT not in new:
            new = new.replace("from app.core.base.markers import", IMPORT + "from app.core.base.markers import", 1)
        path.write_text(new)
        count += n
        files += 1
print(f"replaced {count} in {files} files")
```

Then run `ruff check --fix --select F401,I app/modules` (to drop `func` where it is now unused) and `ruff format app/modules`. Confirm nothing is left:

```bash
grep -rn "select(func.count()).select_from" app/modules
```

Expected: only `observability/repository/incidents.py`, plus any filtered counts that live outside `list_page`.

- [ ] **Step 5: Run.** Run `... pytest tests/core`, then the full backend suite, `lint-imports` and `check_module_boundaries.py --strict`. Expected: everything passes.

- [ ] **Step 6: Commit** `refactor(core): share the list_page query through PageQuery`.

---

### Task 7: Translations, gates and notes

- [ ] **Step 1: Add the keys to `frontend/locales/{en,vi}/common.json` under `errors`,** with a Python JSON edit that keeps two-space indentation and the key order:

| Key | en | vi |
|---|---|---|
| `secret_unreadable` | A saved secret can't be decrypted with the current key. | Không giải mã được một secret đã lưu bằng key hiện tại. |
| `cloudflare_account_token_unreadable` | The saved Cloudflare API token can't be decrypted. Re-enter the token for this account. | Không giải mã được API token Cloudflare đã lưu. Hãy nhập lại token cho tài khoản này. |
| `cloudflare_webhook_secret_unreadable` | The saved Cloudflare webhook secret can't be decrypted. | Không giải mã được secret webhook Cloudflare đã lưu. |
| `loki_credential_unreadable` | The saved Loki credential can't be decrypted. Re-enter it in this environment's Loki settings. | Không giải mã được credential Loki đã lưu. Hãy nhập lại trong cấu hình Loki của môi trường này. |
| `notification_channel_secret_unreadable` | This channel's saved secret can't be decrypted. Re-enter the bot token or webhook URL. | Không giải mã được secret đã lưu của kênh này. Hãy nhập lại bot token hoặc webhook URL. |

- [ ] **Step 2: Run the gates.** Run every command listed in Global Constraints. Expected:
  - ruff clean.
  - 11 import-linter contracts kept.
  - The boundary checker passes.
  - OpenAPI still 65 paths.
  - The full backend suite passes, with more tests than the 723 before this plan.
  - Frontend eslint, `tsc` and vitest pass.
  - GitNexus finds no cycles.
  - No `FernetCodec` import remains outside `app/core/crypto.py` and the four repositories.

- [ ] **Step 3: Write the execution notes and commit.** Append an `## Execution Notes` section to this plan with the commit hashes, test counts and any deviations. Commit `feat(frontend): translate the unreadable-secret errors`.

## Self-Review

- **Spec coverage:**
  - §1 core error, module errors and repository contracts: Tasks 1–4.
  - §1 special paths: Task 2 (webhook verification) and Task 4 (dispatch already caught per channel).
  - §1 frontend translations: Task 7.
  - §2 unit of work: Task 5.
  - §2 pagination: Task 6.
  - §3 cloudflare credentials: Task 2.
  - §4 testing and rollout: every task, plus the Task 7 gates.
- **Refinements made while planning, and reflected in the spec:**
  - `get_credentials` reads the row directly.
  - Webhook access is split into `get_webhook_destination_id` and `get_webhook_secret`.
  - `update_by_environment_id` gains `keep_credential`.
  - `PageQuery.fetch_rows` gains `options` for `rbac`'s `selectinload`.
  - The generic `secret_unreadable` translation is added.
- **Type consistency:** the same names are used in every task: `CloudflareCredentials(account_id, cf_account_id, api_token)`, `get_credentials`, `get_webhook_destination_id`, `get_webhook_secret`, `set_webhook_destination(secret=)`, `get_credential`, `keep_credential`, `get_dispatch_config`, `SqlAlchemyUnitOfWork`, `CachedSqlAlchemyUnitOfWork`, `CacheVersionBumper`, `AbstractCachedUnitOfWork` and `PageQuery.fetch_rows`.

## Execution Notes (2026-09-14)

Branch `refactor/shared-backend-mechanics`, one commit per task:

| Commit | Task |
|---|---|
| `0905253` | design |
| `0541d9b` | plan |
| `eb0b268` | 1 — `SecretUnreadableError` |
| `7c2c355` | 2 — cloudflare `get_credentials` |
| `e47a116` | 3 — Loki credential |
| `91a0dd6` | 4 — notification channel secrets |
| `4ab1156` | 5 — shared unit of work |
| `b7a0179` | 6 — `PageQuery` |
| `f18c5cc` | 7 — translations |

**Results.** Backend 743 tests passed, up from 723 at the branch point. ruff check and format clean, lint-imports 11/11, `check_module_boundaries.py --strict` clean, OpenAPI still 65 paths. Frontend eslint and `tsc --noEmit` clean, vitest 53 passed. GitNexus `check --cycles` found no circular imports; `detect-changes --scope compare --base-ref develop` reports 88 files, 411 symbols, 5 affected processes, medium risk. `FernetCodec` is now imported only by `app/core/crypto.py`, which defines it, and the four repositories that own a secret; `auth/models.py` names it in a docstring only.

**Deviations from the plan, all reflected in the spec:**

- `get_credentials` reads the account row directly instead of through the cache-aside `get_by_id`, so the token never enters the cache.
- Webhook access split into `get_webhook_destination_id`, which never decrypts, and `get_webhook_secret`. Registering an alert rule therefore still works when the stored secret is unreadable.
- `update_by_environment_id` gained `keep_credential`, so a Loki update that doesn't rotate the credential never needs the key.
- `PageQuery.fetch_rows` gained `options`, carrying rbac's `selectinload(Role.permissions)`.

**Two mistakes worth recording:**

- The cloudflare migration script renamed the local `api_token` in `sync_tunnels.py`, which also renamed `_sync_ingress`'s parameter and left the file unparsable. Repaired by hand, and every service file was then re-parsed with `ast` before the tests ran. A rename script needs a scope check, not just a regex.
- The first locale insertion swallowed the indentation of the key that followed it. JSON still parsed, which is exactly why the check has to compare formatting, not only `json.loads`.

**Not verified here:** no browser check of the new 409 messages, and no run against a real Cloudflare, Loki, Telegram or Base.vn account. Backend tests need Docker and `CACHE__URL=redis://localhost:6379/0`.
