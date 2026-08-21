# Design: Advanced permission system (RBAC + dynamic roles)

Status: draft, pending user review
Owner: coderfake
Date: 2026-08-20

## Goal

Replace the current fixed 3-role enum (`OWNER`/`ADMIN`/`MEMBER`, auto-mapped from
DX SSO's external role code) with a real RBAC system: admin-manageable roles,
a fixed `resource:action` permission catalog, and enforcement via a
`require_permission` FastAPI dependency — plus the Next.js admin UI and real
session wiring needed to use it end to end.

## Scope

**In:**
- Backend `rbac` module: `Role`, `Permission`, `RolePermission`, `UserRole` tables, seed script, `require_permission(resource, action)` dependency, admin CRUD for roles.
- Remove `Department` entirely (model, repository, sync branch) and the `UserRole` enum / `RoleMapping` DX-role auto-assignment from `auth`.
- Frontend: `entities/permission` (`PermissionProvider`, `useCan`, `<Can>`), `modules/rbac` admin UI (roles, users), admin pages under `(dashboard)/admin/*`.
- Wiring the real frontend session (`/auth/me`, replacing the placeholder `useAuthSession`) — previously tracked as separate "sub-issue #5," pulled into this task per explicit user decision (2026-08-20 Q&A).
- Router-thinness fix to `auth/router.py` and the matching rule added to `reviewing-code-against-skills` — already done, ahead of this doc, per user request.

**Out:**
- Multi-tenant / organization / department scoping of any kind — explicitly rejected.
- Multiple roles per user — v1 is one active role per user, matching the current single-`role`-column model.
- Restricting which roles a given admin is allowed to grant (e.g. "can't grant a role above your own") — flagged as a risk below, not built in v1.
- Any other ITSM domain module (tickets, assets, CMDB, ...) — none exist yet; the permission catalog only covers real resources (`role`, `permission`, `user`) that exist today.

## Decisions log (from clarifying Q&A, 2026-08-20)

1. Combination: RBAC (`resource:action`) + admin-creatable custom roles + ~~department scoping~~ (walked back — see #4).
2. Full backend + Admin UI in scope (not backend-only).
3. Replace the `UserRole` enum with a dynamic `role` table, seeded with 3 default roles.
4. No department scoping; `Department` removed entirely from the codebase (not just unused for permissions).
5. No DX-role → app-role auto-mapping on login; new users get a fixed default role, admin assigns manually.
6. Permission catalog covers only resources that exist today (role/permission/user management) — no speculative resources for future modules.
7. Real frontend session wiring is in scope for this task.

## Architecture

New `backend/app/modules/rbac/` module (not folded into `auth`), because this
is meant to be the authorization spine every future ITSM domain module plugs
into via `require_permission`, which is a distinct concern from `auth`'s
session/login job. `rbac` depends on `auth`'s `public.py` facade to resolve
"who is the current user"; `auth` never imports from `rbac`. This mirrors
`fastapi-modular-scaffold`'s `references/rbac.md`, adapted for single-tenant
(no `organization_id` anywhere).

## Data model

```python
# app/modules/rbac/models.py
class Role(Base):
    __tablename__ = "role"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # seeded roles: undeletable, unrenamable

class Permission(Base):
    __tablename__ = "permission"
    __table_args__ = (UniqueConstraint("resource", "action"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    resource: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(255))
    # fixed catalog, seeded from code — never admin-created

class RolePermission(Base):
    __tablename__ = "role_permission"
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission.id"), primary_key=True)

class UserRole(Base):
    __tablename__ = "user_role"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, unique=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))
    # unique(user_id): one active role per user in v1 — see Scope > Out
```

`user_role.user_id` FKs cross-module into `auth.users.id` — same pattern as
`references/rbac.md`'s own example, just without `organization_id`. `auth`'s
`User` model drops its `role` enum column entirely; `auth` never needs to know
`Role` exists at the schema level.

## Permission catalog v1

| Resource | Actions | Notes |
|---|---|---|
| `role` | `create`, `read`, `update`, `delete` | `update` covers rename + editing its permission set — a role owns its permission list the same way an order owns its line items |
| `permission` | `read` | Lists the fixed catalog, for building the role-edit checkbox UI. No create/update/delete — not admin-invented, per `rbac.md`'s anti-pattern list |
| `user` | `read`, `update_status`, `assign_role` | `update_status` = block/unblock; identity fields stay DX-sync-owned |

Seeded roles (`is_system=True`): **owner** and **admin** start granted every
permission in the catalog; **member** starts with none (matches the existing
"least privileged role" language already in `auth/rules.py`). All three are
undeletable and unrenamable, but an owner *can* edit what permissions
`admin`/`member` hold — so `PATCH /rbac/roles/{id}` (`role.update`) is
partially locked for an `is_system` role: `name` is rejected, `permissionIds`
is not. This split is a `rules.py` decision (`RbacRules.can_rename(role)` vs.
plain permission-set replacement), not something the router or schema layer
special-cases.

**Bus-factor safety rule** (`rbac/rules.py`, pure `@rule`): block removing the
`owner` role from the last user who holds it, and block deleting/demoting
that same last user — otherwise the system can end up with nobody able to
manage roles or users at all. Identified by `role.name == "owner"` — safe
because `is_system` roles are unrenamable, so this name can never drift.

## Backend flow changes

- `auth`'s `SyncExternalUser` use case: after creating a new user, call
  `RbacApi.assign_default_role(user_id)` (grants `member`) instead of the old
  `AuthRules.resolve_role`/`RoleMapping`. `RoleMapping`, `UserRole` enum, and
  `AuthRules.resolve_role` are deleted.
- `auth`'s `/me` endpoint composes with `rbac`'s facade at the router/service
  layer (never a SQL join) to include `roleName` + `permissions: string[]` in
  the response — this is what the frontend session/`PermissionProvider` seeds
  from.
- New `rbac/router.py` (`/rbac/roles`, `/rbac/permissions`) and additions to
  `auth/router.py` (`GET /auth/users`, `PATCH /auth/users/{id}/status`,
  `PATCH /auth/users/{id}/role`) — every one of these gated by
  `Depends(require_permission(resource, action))` from `rbac`'s facade.
  **Router-thinness applies to both**: translate HTTP → use case only, no
  embedded helpers (already fixed in `auth/router.py`'s cookie/redirect
  handling; `rbac/router.py` is written to the same rule from the start —
  see the `reviewing-code-against-skills` update already merged).

## Frontend

- `entities/permission/` — `PermissionProvider`, `useCan`, `<Can>`, per this
  project's own `nextjs-modular-architecture` → `references/rbac-ui.md`.
  Wired into the same provider tree as `QueryClientProvider`, seeded from the
  verified session only (never a URL param/client state).
- `modules/rbac/` — role list/create/edit (permission checkboxes grouped by
  resource, disabled for `is_system` name/delete), user list + role-assign +
  block/unblock.
- Pages: `(dashboard)/admin/roles`, `(dashboard)/admin/users` — server-guarded
  via `verifySession` + redirect (the real check), `<Can>`/`RequirePermission`
  for UX only.
- Real session: `authSessionSchema` gains `roleName: string` and
  `permissions: string[]`; `fetchAuthSession` calls `/auth/me` for real via
  `apiFetch`; `AuthGuard`/`user-menu`/login button connect to it, replacing
  the placeholder. This subsumes the previously-separate "sub-issue #5."

## Migration

One Alembic migration: drop `departments` table + `users.department_id`, drop
`users.role` column, create `role`/`permission`/`role_permission`/`user_role`
tables. Data migration note: this project has no production data yet (no
migration has run beyond the initial `create_users_departments_dx_tokens`), so
no backfill logic is needed — confirm this is still true before writing the
migration; if real users exist by implementation time, add a backfill step
that seeds `member` for every existing user.

## Testing

- Backend: `rbac/rules.py` unit tests (bus-factor rule, pure); `test_services.py`
  against a `Fake` `AbstractRbacUnitOfWork`; `test_router.py` asserting 403 on
  missing permission and 200 with it; `auth`'s existing test suite updated for
  the removed `Department`/`RoleMapping` code paths.
- Frontend: `<Can>` hide/disable behavior; admin pages redirect when
  unauthorized; role-edit form disables system-role name/delete controls.

## Risks / known simplifications

- **Unrestricted role granting**: any user holding `user.assign_role` can
  assign any role, including `owner`. `rbac-ui.md` recommends filtering the
  grantable-role list by the granter's own permissions; not built in v1 per
  YAGNI, flagged here so it's a conscious choice, not an oversight.
- **No org/department scoping** means this design does not generalize to a
  future multi-tenant requirement without real rework (a deliberate trade
  for simplicity now, per the decisions log).
- Frontend session wiring folded into this task changes its size
  meaningfully — flagged in Scope > In, not hidden in the middle of
  implementation.

## Skills applied

- `fastapi-modular-scaffold` (`references/rbac.md`, `references/layer-examples.md`, rule #10 router-thinness — enforcement already added to `reviewing-code-against-skills/references/backend-checks.md`)
- `nextjs-modular-architecture` (`references/rbac-ui.md`, `references/data-layer.md` for the real session prefetch)
- `reviewing-code-against-skills` — governs Phase 4 review of this work, including the router-thinness section added 2026-08-20
