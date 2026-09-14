# DX SSO Logout and DX Token Ownership — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align ITSM's DX SSO integration with dx-core-service `70c9c8a` (branch `feature/sso-logout-and-consent-sync`):
- Move DX token storage from `integrations/dx_core` into the `auth` module.
- Revoke both DX tokens on logout.
- Let the user choose, in a logout confirmation dialog, whether to also end their DX SSO session.
- Accept a userinfo response that has no `name`.

**Architecture:**
- **`dx_core` integration.** Stays transport only: PKCE, authorize URL, token exchange, userinfo, revoke, and a new logout URL builder. It owns no table.
- **`auth` module.** Owns `dx_tokens` (model, repository, Fernet key). The table is reached through `AuthUnitOfWork.dx_tokens`, the same way `NotificationsUnitOfWork.channels` works.
- **Logout API.** `POST /auth/logout` takes an optional `{endDxSession}` and returns `{dxLogoutUrl}`.
- **Frontend.** Asks for confirmation first. When the switch is on, it navigates the browser to that URL after the local session is cleared.

**Tech Stack:** FastAPI, SQLAlchemy async, pydantic-settings 2.15, httpx; Next.js 16, TanStack Query 5, zod 4, next-intl 4, Base UI 1.7 (shadcn base-nova), vitest.

**Spec:** User decisions on 2026-09-14:
- **Token storage:** "Giữ, chuyển về auth" (keep the tokens, move them into `auth`).
- **Logout:** "1 switch trên UI cho phép đăng xuất cả 2 hoặc chỉ itsm trước khi logout gọi modal confirm logout lên" (show a confirmation modal before logout, with a switch to sign out of both ITSM and DX or only ITSM).
- **Fernet key:** "AUTH__, đọc tên cũ dự phòng" (use `AUTH__`, keep reading the old name as a fallback).

The DX contract is taken from dx-core-service `docs/sso.md` and `src/modules/auth/oauth2.controller.ts` at `70c9c8a`.

## Global Constraints

- Branch `feature/dx-sso-logout-and-token-ownership` from `develop` (`3dade31`). Local commits only.
- **fastapi-modular-scaffold:**
  - An integration owns no tables ("no `models.py` because it owns no tables").
  - Rule #15: `Abstract*` contracts.
  - Rule #18: intra-module import order.
  - Rule #11: the env prefix mirrors the folder name.
  - Rule #10: routers hold no business logic.
  - Rule #16: class-scoped constants.
- **nextjs-modular-architecture:**
  - Fetchers validate the response with a zod schema from `model/`.
  - No module-to-module imports.
  - shadcn source lives in `shared/ui/`.
  - Errors are shown by translating `error.code`.
- **ui-ux-pro-max:**
  - Confirm before an action that is hard to undo.
  - Every input has a visible label.
  - Icon-only buttons have an accessible name.
- No database migration: the table name `dx_tokens` does not change.
- Existing env files keep working: `DX_CORE__FERNET_KEY` is read as a fallback for `AUTH__DX_TOKEN_FERNET_KEY`. This was verified with pydantic-settings `AliasChoices`:
  - The new name wins when both are set.
  - The old name is read from both the environment and the `.env` file.
  - `env_prefix` still applies to the other fields.

## DX contract (verified at dx-core-service 70c9c8a)

| Endpoint | Behaviour ITSM depends on |
|---|---|
| `POST /oauth2/token` | Client authenticates with HTTP Basic. Returns `access_token` (JWT, 900 s), `refresh_token` (opaque, 7 days), `token_type`, `expires_in`, and optionally `scope`. |
| `GET /oauth2/userinfo` | Returns `sub`, `email`, `name`, `employeeCode`, `emailVerified`, `roles[]`, `department{id,code,name}` or null, `scope`, `permissions[]`. `name` is omitted when the DX user has no full name. |
| `POST /oauth2/revoke` | Client authenticates with HTTP Basic. A JWT has its `jti` blacklisted; any other value marks the matching refresh token revoked. |
| `GET /oauth2/logout?client_id&post_logout_redirect_uri` | Browser navigation, using the `sso_sid` cookie. It destroys the SSO session, revokes the tokens tied to that `sso_sid` and every refresh token of the (user, client) pair, then redirects. The target is the client's registered `post_logout_redirect_uri` when the parameter is absent or equal to it; otherwise it is the DX login page. |

## Impact Assessment (GitNexus, upstream)

| Symbol | Risk | Mitigation |
|---|---|---|
| `DxCoreClient`, `DxUserProfile` | MEDIUM (8 direct) | Changes are additive: optional `transport`, optional `name`, a new `build_logout_url`. `refresh()` has no caller. Covered by new client tests and the router tests. |
| `AuthConfig` | MEDIUM (5 direct) | One field is added, with an alias. Existing fields are untouched. |
| `LogoutUser`, `SyncExternalUser`, `AuthenticateWithDx`, `AuthUnitOfWork`, `get_logout_user`, `get_dx_token_repository` | LOW | Constructor changes stay inside auth wiring and tests. Affected flows: `logout`, `get_authenticate_with_dx`. |
| `useLogout`, `UserMenu`, `DashboardSidebar` | LOW (`DashboardLayout` / `DashboardShell` flows) | The dialog only sits in front of the existing mutation. |
| `ConfirmDialog` | **CRITICAL** (18 direct, 23 flows) | **Not edited.** `LogoutDialog` composes the generic `Dialog` shell instead. |

## Tasks

### Task 1: dx_core client matches the DX contract

**Files:**
- `tests/integrations/dx_core/{__init__,test_client}.py`
- `app/integrations/dx_core/{client,constants,config,exceptions}.py`
- `frontend/locales/{en,vi}/modules/auth.json` (removed error codes only)

- [ ] **Write failing tests using `httpx.MockTransport`:**
  - userinfo without `name` parses.
  - A malformed userinfo or token body raises `DxCoreUnavailable`.
  - A 400 from the token endpoint raises `TokenExchangeFailed`.
  - `revoke` posts `{token}` with Basic auth and swallows a 5xx or a transport error.
  - `build_logout_url` carries `client_id`, and adds `post_logout_redirect_uri` only when `DX_CORE__POST_LOGOUT_REDIRECT_URI` is set.
- [ ] **Implement:**
  - `DxCoreClient(transport=None)`.
  - `DxUserProfile.name: str | None`.
  - Map pydantic `ValidationError` to `DxCoreUnavailable`.
  - Add `DxEndpoints.LOGOUT` and `DxCoreConfig.POST_LOGOUT_REDIRECT_URI`.
  - Add `build_logout_url()`.
- [ ] **Remove the unused refresh scaffolding:**
  - `DxCoreClient.refresh`.
  - `DxDefaults.REFRESH_LOCK_*` and `ACCESS_TOKEN_EXPIRY_SKEW_SECONDS`.
  - `DxCacheNamespaces.REFRESH_LOCK`.
  - `DxNotLinked`, `DxRefreshFailed`, their `DxErrorCode` members and their translations.
- [ ] Commit: `feat(dx-core): parse the current userinfo contract and build the DX logout URL`

### Task 2: DX tokens owned by auth

**Files:**
- `app/modules/auth/{models,repository,uow,config,dependencies}.py`
- `app/modules/auth/utils/wiring.py`
- `app/modules/auth/services/{authenticate,logout,issue_tokens}.py`
- `alembic/env.py`
- Removed: `app/integrations/dx_core/{models,repository}.py`
- Tests: `tests/auth/{test_repository,test_config,test_services,test_router}.py`

- [ ] **Write failing tests:**
  - `AuthConfig` reads `AUTH__DX_TOKEN_FERNET_KEY` and falls back to `DX_CORE__FERNET_KEY`.
  - `DxTokenRepository` round-trips both tokens encrypted, against real Postgres.
  - `AuthenticateWithDx` saves through `uow.dx_tokens`.
- [ ] **Implement:**
  - `git mv` the model and repository into `auth`.
  - Read the key from `auth_settings.DX_TOKEN_FERNET_KEY`.
  - Add `decrypt_refresh_token`.
  - Add `AuthUnitOfWork.dx_tokens` and drop `get_dx_token_repository`.
  - `alembic/env.py` imports `app.modules.auth.models`.
  - `DxCoreConfig` drops `FERNET_KEY`.
- [ ] Commit: `refactor(auth): own the dx_tokens table and its Fernet key`

### Task 3: logout revokes both DX tokens and can end the DX session

**Files:**
- `app/modules/auth/{schemas,router}.py`
- `app/modules/auth/services/{logout,sync_external_user}.py`
- `tests/auth/{test_services,test_router}.py`

- [ ] **Write failing tests:**
  - `LogoutUser` revokes the refresh token and then the access token, clears the row, and blacklists the app tokens.
  - `LogoutUser` returns the DX logout URL only when `end_dx_session` is true.
  - The router accepts an optional `{endDxSession}` body and returns `{dxLogoutUrl}`.
  - When DX omits `name`, `SyncExternalUser` uses the email for a new user and keeps the stored name for an existing one.
- [ ] Implement.
- [ ] Commit: `feat(auth): revoke both DX tokens on logout and optionally end the DX session`

### Task 4: logout confirmation dialog with a DX session switch (UI; invoke ui-ux-pro-max)

**Files:**
- `frontend/src/shared/ui/switch.tsx`
- `frontend/src/modules/auth/model/logout.ts`
- `frontend/src/modules/auth/api/logout.ts`
- `frontend/src/modules/auth/hooks/use-logout.ts`
- `frontend/src/modules/auth/ui/logout-dialog.tsx` and its test
- `frontend/src/modules/auth/ui/user-menu.tsx`
- `frontend/src/modules/auth/index.ts`
- `frontend/src/app/[locale]/(dashboard)/dashboard-sidebar.tsx`
- `frontend/locales/{en,vi}/modules/auth.json`

- [ ] **Build `LogoutDialog`:**
  - Compose `Dialog`, not `ConfirmDialog`.
  - Use the Base UI `Switch` with a visible label and hint, wired through `aria-labelledby` / `aria-describedby`.
  - The switch is off by default and resets when the dialog closes.
  - The confirm button shows a pending state.
- [ ] **Update `useLogout`:**
  - Variables: `{endDxSession}`.
  - The response is parsed with `logoutResultSchema`.
  - `onSuccess` clears the query cache, then calls `window.location.assign(dxLogoutUrl)` when a URL is returned, otherwise `router.replace(ROUTES.login)`.
- [ ] `UserMenu` and `DashboardSidebar` open the dialog instead of calling the mutation directly.
- [ ] Commit: `feat(frontend): confirm logout and let the user end the DX session too`

### Task 5: configuration, docs and verification

- [ ] `.env.example`: add `AUTH__DX_TOKEN_FERNET_KEY` (with a note that `DX_CORE__FERNET_KEY` is still read) and `DX_CORE__POST_LOGOUT_REDIRECT_URI`.
- [ ] README: update the settings table and document the logout choice.
- [ ] `docs/tasks/sso-login.md`: add ITSM notes to §9 (refresh) and §10 (logout).
- [ ] **Backend gates:**
  - `ruff check` and `ruff format --check`.
  - `lint-imports` 11/11.
  - `check_module_boundaries.py --strict`.
  - OpenAPI path count unchanged (65).
  - Full `pytest`.
- [ ] **Frontend gates:** `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm test`.
- [ ] **GitNexus:** `detect-changes --scope compare --base-ref develop` and `check --cycles`.
- [ ] Commit: `docs: document the DX token key, post-logout URI and logout choice`

## Risks

- **DX may not be deployed yet.** `70c9c8a` is not on dx-core-service `main`. Until it is deployed, `/oauth2/logout` sends clients outside `weupbook.com` to the DX login page. ITSM's client also needs a registered `post_logout_redirect_uri` on DX.
- **Ending the DX session has side effects.** It stops silent login for every DX app in that browser, which is why the switch is opt-in and off by default.
- **Revoked refresh tokens must not be reused.** `/oauth2/revoke` leaves `revokedReason` empty. Reusing that token would trigger DX theft detection for the user–client pair. ITSM deletes the row immediately, so the token is never reused.

## Execution Notes (2026-09-14)

- Commits on `feature/dx-sso-logout-and-token-ownership`: `5d23f0f` (plan), `22bba7d` (Task 1), `8d365ca` (Task 2; git records the model and repository as renames), `bc87513` (Task 3), then Task 4 and Task 5.
- Backend: 721 tests passed (698 before; +13 client, +4 config, +3 repository, +3 service), ruff clean, lint-imports 11/11, module boundaries ok, OpenAPI still 65 paths.
- Frontend: vitest 53 passed (+6 `LogoutDialog`), eslint and `tsc --noEmit` clean.
- GitNexus rated Task 3 HIGH (8 flows) because the login callback and logout both run through the changed use cases; `tests/auth/test_router.py` covers both flows end to end against real Postgres and Redis.
- `ConfirmDialog` (CRITICAL) was not touched; `LogoutDialog` composes `Dialog`.
- Not verified here: the flow against a real WeUp DX, which needs dx-core-service `70c9c8a` deployed and a `post_logout_redirect_uri` registered for the ITSM client, and a manual browser check of the dialog.
