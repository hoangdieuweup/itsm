# Users Module Split — Design

**Owner:** coderfake · **Date:** 2026-08-21 · **Status:** approved, pending implementation plan

## Goal

Split user administration out of `auth` into its own `users` module, so `auth` is left owning only session/SSO concerns (JWT, cookies, the DX OAuth2 flow) and `users` owns the `User` entity, its CRUD, and the account-protection rules that currently live in `auth` only because `auth` happened to own the table first.

## Why now

`auth` has been accumulating two unrelated responsibilities: proving who is making a request (session), and administering user accounts (list/block/unblock, the protected break-glass admin account). The RBAC work already established the pattern for a module reaching another module's entity only through its `public.py` facade — this split applies that same discipline to `auth` itself.

No database migration: `users` owns the same `users` table under a new Python module, same columns, same name. This is a pure code-organization change.

## Module boundary

**Moves to `app/modules/users/`:**
- `User` ORM model (`models.py`), `UserRepository`/`AbstractUserRepository` (`repository.py`), `UsersUnitOfWork`/`AbstractUsersUnitOfWork` (`uow.py`)
- `UserRead`, `UserStatusUpdate` schemas
- `UpdateUserStatus` use case (block/unblock — an administrative action on an account, not a session action)
- `UsersConfig.ADMIN_EMAIL`/`ADMIN_NAME` (env prefix becomes `USERS__`, was `AUTH__`), `UsersRules.is_protected_admin_email`, `CannotModifyProtectedAdmin`, `CannotBlockLastAdmin` — these guard a *user account* from admin actions, not login
- `UserCreated` event (a fact about the entity, not about a login)
- `GET /users`, `PATCH /users/{id}/status` — moves to a new `/api/v1/users` prefix (was `/api/v1/auth/users`)
- `users/public.py`: `UsersApi` facade exposing `get_user_by_id`, `is_protected_admin`, `find_by_email`, `find_by_external_id`, `create`, `update_profile`, `set_last_login`, and `invalidate_user` (see Transaction & cache-invalidation ownership below)

**Stays in `auth`:**
- JWT issuance/decoding, session cookies, the DX OAuth2 flow, `AuthenticateWithDx`, `SyncExternalUser` (now calling `UsersApi` instead of owning a repository), `IssueTokens`, `LogoutUser`, the token blacklist
- `AuthRules.can_login`, `UserBlocked`, `NotAuthenticated` — session-time decisions, even though they read a `users`-owned status field
- `MeResponse` (composes `users`' `UserRead` + rbac's role/permissions — still "what can the current session do")
- `UserLoggedIn` event
- `/oauth/dx/*`, `/logout`, `/me`

**Structural consequence:** `auth` owns zero tables after this split. It keeps a request-scoped transaction coordinator (see below) but no `models.py`/`repository.py` of its own — shaped closer to how the skill describes an integration module ("no models.py because it owns no tables") than a typical domain module, even though it keeps a `router.py`/`services/` full of real business logic.

## Cross-module dependency shape

```
auth   → users   (resolve current user; sync DX profile)
users  → rbac    (bus-factor check in UpdateUserStatus, unchanged from today)
rbac   → users   (existence/protection checks in AssignRole — moved from auth.public)
rbac   → auth    (session resolution in require_permission — unchanged from today)
```

This closes a 3-way cycle at the `public.py` level: `auth → users → rbac → auth`. Legal under the module-boundary rule (it only forbids reaching past `public.py`, not bidirectional module dependencies), but the same class of problem already hit once this session between `auth` and `rbac`: FastAPI's `Depends()` evaluates default values at function-definition time, so a composition-root factory that needs types from a module which transitively imports back to its own module raises `ImportError` at server startup, not at review time.

**Mitigation, same as the precedent:** any `dependencies.py` factory whose parameters span modules that would close the cycle moves into that module's own `router.py` (a leaf, never imported by anything else) instead of `dependencies.py`. The exact set of factories affected will be determined during implementation by running `scripts/check_module_boundaries.py` and a real `app.main` import — reasoning about it in the abstract wasn't reliable last time either.

## Transaction & cache-invalidation ownership

The trap: `AuthenticateWithDx` currently commits one transaction covering DX-token-save + user create/update + role assignment + last-login update — a real atomicity guarantee (nothing partially applies on failure). After the split, the writes to `users`-owned data happen through `UsersApi`'s facade, but the actual `.commit()` needs to stay owned by `auth`'s flow to preserve that atomicity.

`rbac`'s `AssignDefaultRole` already established the "no self-commit, participate in the caller's shared session" pattern for this — and its `mark_stale` is deliberately skipped because it's provably only ever called for a brand-new `user_id` (nothing could be cached yet). **That reasoning does NOT carry over to `users`' `update_profile`**: it runs on *every* login for a *returning* user, whose `UserRead` is very likely already cached (from `/auth/me`, a permission check, anything). If `users`' own `UsersUnitOfWork.mark_stale()` gets called during this composition but that uow's `.commit()` never fires (auth's coordinator commits instead), the invalidation silently never happens — a real staleness bug, not a harmless no-op.

**Design:** `auth` keeps a minimal coordinator (`AuthUnitOfWork` with no owned repository, wrapping the shared request-scoped session, `commit()`/`rollback()` only) as the actual transaction boundary for the login flow. `UsersApi` exposes an explicit `invalidate_user(user_id: int) -> None` facade method — a thin pass-through to `bump_version` — for exactly this cross-module case. `AuthenticateWithDx` calls `await self._users_api.invalidate_user(user.id)` immediately after its own `await self._uow.commit()` succeeds, for both the create and update_profile paths (cheap and always-correct to call even on the create path, where it's a no-op against nothing-cached-yet, same as today's reasoning for `assign_default_role`). This keeps invalidation strictly-after-commit (caching.md's rule) while letting the commit itself stay owned by whichever module needs the atomicity guarantee.

## Confirmed decisions

- **Module name:** `users` (plural — matches the table name).
- **API prefix:** moves to `/api/v1/users` (was `/api/v1/auth/users`) — a breaking change for the frontend's API client, accepted since these endpoints are new/lightly used so far.
- **Env var:** `AUTH__ADMIN_EMAIL`/`AUTH__ADMIN_NAME` become `USERS__ADMIN_EMAIL`/`USERS__ADMIN_NAME` (rule #11: env prefix mirrors the owning module). Requires updating the already-seeded local `.env` and `.env.example` — a real operational step, not just a rename in code.
- **Error codes:** existing codes prefixed `auth_` for what's moving (`auth_user_not_found`, `auth_cannot_block_last_admin`, `auth_cannot_modify_protected_admin`) become `users_`-prefixed. This is a breaking change for the frontend's i18n error-code mapping for these three codes specifically — flagged for the plan's test/verify checklist, not something to silently carry over as `auth_`-prefixed dead naming in a module that no longer owns them.

## Out of scope

- No database migration (same table, same columns).
- No change to `rbac`'s own schema, seed script, or permission catalog (`resource="user"` stays as the permission resource name — it describes the *business concept* "user account," not the Python module boundary).
- Frontend changes beyond what's needed to point at the new endpoint/error-code prefixes — the frontend's own `entities/user/` restructuring (if any) is a separate, not-yet-scoped piece of work.
