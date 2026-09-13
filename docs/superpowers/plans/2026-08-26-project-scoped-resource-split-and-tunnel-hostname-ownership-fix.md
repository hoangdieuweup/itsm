# Project-Scoped Resource Split + Tunnel/Hostname Ownership Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Close a confirmed, currently-exploitable cross-tenant privilege escalation: a Project-A-only collaborator holding a `ProjectRole` can today delete a tunnel serving Projects B/C/D, reveal its live connector token, and create/edit/delete hostnames belonging to a different environment on the same Cloudflare account. (2) Give the project-scoped authorization surface its own distinct resource names and its own distinct check, so that "edit a tunnel inside my project" and "edit a tunnel on the Cloudflare account" are never the same permission and never satisfied by the same grant.

**Architecture:** The security fix and the naming split are the *same* mechanism, not two features. Each of the 8 currently-project-assignable resources is split into an account-level name (unchanged, never in `ASSIGNABLE`) and a new `project_`-prefixed name (the only one in `ASSIGNABLE`). `require_cloudflare_environment_access` grows from one `(resource, action)` pair to two resource names — the account-manager path keeps checking the OLD name, the project-role path checks the NEW one — and the two genuinely dangerous atoms (`cloudflare_tunnel.delete`, `cloudflare_tunnel.reveal_token`) pass `None` as the project resource, structurally removing the project path from those routes. Independently, the three hostname write use cases gain the environment-ownership guard DNS has had since `8a79eab65342`, so the remaining project-assignable hostname atoms are actually safe to grant.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, pytest + testcontainers Postgres 16; Next.js App Router, TanStack Query, next-intl, vitest.

**Spec:** This document IS the spec. It extends `docs/superpowers/plans/2026-08-25-project-scoped-permissions.md` and `docs/superpowers/plans/2026-08-25-environment-scoped-cloudflare-loki-alerting-project-roles.md` (both shipped). Read the latter's D1–D9 for context on `resolve_project_permissions` / `ProjectScopedPermissionCatalog` / the composed cloudflare dependency being modified here.

## Global Constraints

- Never touch the live `itsm` database — all manual verification targets `itsm_test` on `localhost:5435`.
- `cloudflare_tunnel.delete` and `cloudflare_tunnel.reveal_token` must never appear in `ProjectScopedPermissionCatalog.ASSIGNABLE` again, under any name, ever — same permanent-exclusion tier as `cloudflare_config.manage`.
- Migration before seed, always, every environment.
- No `.importlinter` changes needed — `projects-facade` already permits `app.modules.cloudflare` to import `projects.public`.
- User explicitly confirmed (twice, via direct questions): the security fix (remove tunnel.delete/reveal_token from project-assignable; fix hostname ownership checks) AND the resource-naming split should be done together in one plan, not sequenced. Also confirmed: the permission-level split (not literal duplicate HTTP routes) is the correct interpretation of "separate API, not shared."

---

## Context

While doing manual verification of the just-shipped "environment-scoped-cloudflare-loki-alerting-project-roles" feature, the user flagged (via a live screenshot + follow-up messages) that editing a Tunnel from inside a project should be a *different, narrower* capability than editing a Tunnel on the Cloudflare account — "vì tunnel trong cloudflare là được sửa nhiều thứ" (because a Cloudflare tunnel touches many things), "còn trong project chỉ sửa/thêm của project đó thôi" (whereas in a project you should only edit/add things belonging to that project). Two Explore agents + one Plan agent (dispatched from Claude Code's native plan mode) confirmed this is not just a style concern — it's a real, currently-exploitable cross-tenant privilege-escalation bug, and traced it to its root: `CloudflareTunnel` has no `environment_id` at all (only `cloudflare_account_id` — a tunnel commonly serves several unrelated projects, e.g. "macm4" serving agent-mkt/itsm/social/dx per the earlier "Bug Fix — Cloudflare Tunnel Environment Scoping"), and the ownership check every tunnel/hostname write use case relies on (`TunnelOwnershipRules.verify_tunnel_belongs_to_environment`, misleadingly named) only ever verifies the *account* matches, never the *environment*. Combined with `cloudflare_tunnel.delete`, `.reveal_token`, and `cloudflare_hostname.create/update/delete` being listed in `ProjectScopedPermissionCatalog.ASSIGNABLE`, a user who is only a member of Project A — with zero real Cloudflare account access — can today delete a tunnel serving Projects B/C/D, reveal its live connector token, and create/edit/delete hostnames belonging to a different project on the same account.

The user separately confirmed they want two things done together, not sequenced: (1) fix the security bug, and (2) give project-scoped permissions their own distinct resource names with a genuinely separate authorization check from the Cloudflare-account-level surface — "vừa tạo tên riêng lại vừa thêm api vào project không dùng chung api với bên khác." A dedicated Plan agent (Opus) then read every relevant file end-to-end and designed the concrete scheme below, including verifying (by grep, not assumption) that the composite `"resource.action"` permission-check strings are never parsed back apart anywhere in the codebase — which is what makes an underscore-based rename safe.

**Intended outcome:** the two authorization surfaces become structurally incapable of aliasing each other. A project role can only ever hold `project_`-prefixed atoms; the two genuinely account-wide tunnel actions (`delete`, `reveal_token`) have no project-scoped counterpart at all; and the two hostname mutation gaps get the same per-environment ownership check DNS records have had since the earlier DNS Record Environment Scoping fix.

## Decisions

**D1 — Separator is underscore (`project_cloudflare_tunnel`), not dot.** Verified by grep, not assumed: `backend/tests/projects/test_services.py`'s `FakeRbacApi` does `key.split(".")[0]`/`[1]` on a permission key, and next-intl treats `.` as an object-nesting separator in the locale JSON (`catalog.${descriptionKey}` lookups in `project-role-form-dialog.tsx`/`role-form-dialog.tsx`) — a dotted resource string would silently break both. No code anywhere parses an underscored resource string apart.

**D2 — The exact split.** 5 of the 8 currently-assignable resources have zero global/account-level call sites today (cleanly project-scoped already) and get a straight rename, retiring the old string entirely: `cloudflare_hostname`→`project_cloudflare_hostname`, `loki_config`→`project_loki_config`. `cloudflare_dns`, `cloudflare_tunnel`, `cloudflare_audit` also get a `project_` twin but keep the old name too, since `cloudflare_config.read`, `alert_rule.read`, and `incident.read` are *also* checked as bare global permissions elsewhere (the account-level zone picker `GET /cloudflare-accounts/{id}/zones`, the account-level `GET /cloudflare-accounts/{id}/available-alerts`, and the deliberately-global `GET /incidents` list) — those three must keep their old name for that other route, and gain a new `project_` name for everything else. Full table:

| Old name (kept?) | Actions it keeps | New `project_` name (the only one in `ASSIGNABLE`) | Actions |
|---|---|---|---|
| `cloudflare_config` (kept, account-only) | `read` (zone picker), `manage` | `project_cloudflare_config` | `read` |
| `cloudflare_dns` (kept, unused after split — no other route checks it, but kept for symmetry/possible future account-level DNS route) | none currently | `project_cloudflare_dns` | `read,create,update,delete` |
| `cloudflare_tunnel` (kept, account-only) | `read,create,sync,refresh_status,delete,reveal_token` | `project_cloudflare_tunnel` | `read,create,sync,refresh_status` — **no delete, no reveal_token, ever** |
| `cloudflare_hostname` (retired) | — | `project_cloudflare_hostname` | `read,create,update,delete` |
| `cloudflare_audit` (kept, unused after split) | none currently | `project_cloudflare_audit` | `read` |
| `loki_config` (retired) | — | `project_loki_config` | `read,manage` |
| `alert_rule` (kept, account-only) | `read` (available-alerts route only) | `project_alert_rule` | `create,read,update,delete` |
| `incident` (kept, global-only) | `read` (cross-project list only) | `project_incident` | `create,read,acknowledge,resolve` |

Catalog grows 65→81 rows (24 added, 8 retired: `loki_config.{read,manage}`, `alert_rule.{create,update,delete}`, `incident.{create,acknowledge,resolve}`). `ProjectScopedPermissionCatalog.ASSIGNABLE` shrinks from 35 to 33 tuples (the 26 cloudflare/observability entries become 24 — net -2, because `cloudflare_tunnel.delete`/`.reveal_token` simply have no replacement).

**D3 — `require_cloudflare_environment_access` takes two resource names, not one.** New signature: `require_cloudflare_environment_access(account_resource: str, project_resource: str | None, action: str, min_level: AccessLevel)`. The account-manager path (tried first) checks `account_resource` — **unchanged from today**, so every existing account-manager workflow keeps working byte-for-byte. The project-role fallback checks `project_resource` — the new name — and is only even attempted when `project_resource is not None`. For `cloudflare_tunnel.delete`/`.reveal_token`, pass `project_resource=None`: this isn't a permission that's merely excluded from `ASSIGNABLE`, the fallback branch is structurally skipped, so no future catalog change can accidentally reopen it. `require_project_permission_for_environment`/`_for_alert_rule`/`_for_incident` in observability keep their single-resource signature (they have no account-manager path to preserve) — just point their call sites at the new `project_*` names.

**D4 — Migration must move existing grants, not just rename the constant.** `seed_rbac.py` deletes any `Permission` row no longer in the catalog, cascading to delete every `RolePermission`/`project_role_permissions` link — a bare rename would silently strip every role's existing grants on next seed. A new Alembic data migration (down_revision off the confirmed current head `a3f7d9c2e5b1`) must, in order: (1) insert every new `project_*` permission row, (2) for each old→new pair, **copy** `role_permissions` grants where the old row is kept (an existing global grant must keep working through the fallback's global-UNION half) and **move** them where the old row is retired, (3) delete every `project_role_permissions` grant on an *old* (account-level) resource string outright — a project role must never hold one, that's the bug — and separately delete any `project_role_permissions` grant on `cloudflare_tunnel.delete`/`.reveal_token` with no replacement (this is the actual security fix, and is intentionally irreversible in `downgrade()`), (4) delete the fully-retired old rows itself (not leaving it to `seed_rbac.py`, so the operation is atomic). **Deployment order is load-bearing: `alembic upgrade head` before `python -m app.seeds.seed_rbac`, always** — running the seed first against the new catalog would delete the retired rows (and their grants) before the migration can move them.

**D5 — "Separate API, not shared" is satisfied by the permission split, not by duplicating routes.** Verified and confirmed with the user: the Cloudflare-account-level API is *already* a physically separate route family with separate use cases (`POST/DELETE /cloudflare-accounts/{id}/tunnels[...]` → `CreateAccountTunnel`/`DeleteAccountTunnel`, `GET/POST/PATCH/DELETE /cloudflare-accounts/{id}/zones/{zone_id}/dns-records` → the `*AccountDnsRecord` use cases) — the project-facing `/environments/{id}/...` family is already distinct at the URL level. What was *not* separate was the permission and the ownership check, which D2-D4 now fix. Duplicating `/environments/{id}/cloudflare-tunnels` into a parallel URL calling the identical service would add a redundant `project_id` to cross-validate (a new failure mode) for zero additional safety once the permission split lands. The split is still a literal API-surface change, not just internal bookkeeping: after this fix the project-facing surface genuinely contains no "delete tunnel" or "reveal tunnel token" operation at all (`project_resource=None` removes it structurally).

**D6 — Hostname *create* guard: reject only a positive claim on a sibling's own domain, not any unmatched hostname.** Reuses the existing `TunnelHostnameRules.match_environment_id` pure matcher (already used by `sync_tunnels.py` to *attribute* hostnames) in a new `TunnelHostnameRules.claims_another_environment(hostname, environment_id, candidates) -> bool`: true iff the hostname matches a **different** sibling environment's `base_url`. A hostname matching nothing is the routine case (publishing `api.x.com` when `base_url` is `app.x.com`) and must stay allowed — rejecting it would break normal use for zero safety gain.

**D7 — Hostname *update*/*delete* guard is strict equality (`existing.environment_id != environment_id`), NULL included.** Mirrors `update_dns_record.py`/`delete_dns_record.py`'s existing, already-correct guard exactly. The graduated alternative (only reject when `existing.environment_id is not None`) would still let an attacker repoint a sibling's hostname whenever that sibling has no `base_url` configured — it doesn't close the bug. `ListTunnelHostnames` already filters by `environment_id`, so an unattributed (NULL) hostname is already invisible on every environment's own page today; making it uneditable too just matches what the UI already shows.

**D8 — Frontend gating rule.** `<Can>`/`hasPermission`/sidebar (reads the global session set) keep the **old** account-level names. `<CanInProject>` (reads the project effective set) uses the **new** `project_*` names. Two specific exceptions inside `tunnels-manager.tsx`: the reveal-token and delete buttons stay gated on `<CanInProject I=... a={PERMISSIONS.CLOUDFLARE_TUNNEL.RESOURCE}>` — the **account-level** name — since `CanInProject` reads global∪project-role and `cloudflare_tunnel.delete`/`.reveal_token` can now only ever arrive via the global half; this correctly shows the buttons to exactly the users the backend will allow.

**D9 — Three pre-existing, permanently-dead `MANAGE` gates get fixed while editing those exact lines.** `cloudflare_tunnel.manage`, `cloudflare_hostname.manage`, `cloudflare_dns.manage` don't exist anywhere in `RbacPermissionCatalog.CATALOG` — `tunnels-manager.tsx`, `tunnel-hostnames-panel.tsx`, `dns-manager.tsx` all gate real buttons on them, hiding those controls from *everyone including admins* today. Fixed as part of the same edits (split into the correct per-action gates: `CREATE`/`UPDATE`/`DELETE`/`REFRESH_STATUS` etc.), not silently left broken.

---

## Task 1: Split the RBAC permission catalog

**Files:**
- Modify: `backend/app/modules/rbac/constants.py` (`RbacPermissionCatalog.CATALOG` lines 26-106; `RbacResources` lines 109-135)
- Test: `backend/tests/rbac/test_constants.py`

- [ ] **Step 1: Write the failing test**

Replace the body of `TestRbacPermissionCatalog` in `backend/tests/rbac/test_constants.py`:

```python
class TestRbacPermissionCatalog:
    def test_catalog_includes_alert_rule_and_incident_permissions(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ("project", "manage_all") in resources_actions
        assert ("project_role", "read") in resources_actions
        assert ("project_role", "manage") in resources_actions
        assert len(RbacPermissionCatalog.CATALOG) == 81

    def test_project_scoped_resources_are_distinct_names_not_aliases(self) -> None:
        """The project surface must never be checkable under an account-level
        resource string — that aliasing IS the escalation bug this splits."""
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        for action in ("read", "create", "sync", "refresh_status"):
            assert ("project_cloudflare_tunnel", action) in resources_actions
        for action in ("read", "create", "update", "delete"):
            assert ("project_cloudflare_hostname", action) in resources_actions
            assert ("project_cloudflare_dns", action) in resources_actions
            assert ("project_alert_rule", action) in resources_actions
        assert ("project_cloudflare_config", "read") in resources_actions
        assert ("project_cloudflare_audit", "read") in resources_actions
        for action in ("read", "manage"):
            assert ("project_loki_config", action) in resources_actions
        for action in ("create", "read", "acknowledge", "resolve"):
            assert ("project_incident", action) in resources_actions

    def test_dangerous_tunnel_atoms_have_no_project_scoped_twin(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ("cloudflare_tunnel", "delete") in resources_actions
        assert ("cloudflare_tunnel", "reveal_token") in resources_actions
        assert ("project_cloudflare_tunnel", "delete") not in resources_actions
        assert ("project_cloudflare_tunnel", "reveal_token") not in resources_actions

    def test_retires_resources_whose_only_call_sites_became_project_scoped(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ("loki_config", "read") not in resources_actions
        assert ("loki_config", "manage") not in resources_actions
        for action in ("create", "update", "delete"):
            assert ("alert_rule", action) not in resources_actions
        for action in ("create", "acknowledge", "resolve"):
            assert ("incident", action) not in resources_actions
        # Retained: each still guards one genuinely account/global-level route.
        assert ("alert_rule", "read") in resources_actions
        assert ("incident", "read") in resources_actions
        assert ("cloudflare_config", "read") in resources_actions

    def test_description_key_always_embeds_its_own_resource(self) -> None:
        for resource, action, description_key in RbacPermissionCatalog.CATALOG:
            assert description_key == f"permissions.{resource}.{action}"
```

- [ ] **Step 2: Run to verify it fails**

`cd backend && uv run pytest tests/rbac/test_constants.py -v` → FAIL (count is 65, no `project_*` rows).

- [ ] **Step 3: Implement**

In `backend/app/modules/rbac/constants.py`, edit `CATALOG`:

Delete these 8 lines:
```python
        ("loki_config", "read", "permissions.loki_config.read"),
        ("loki_config", "manage", "permissions.loki_config.manage"),
        ("alert_rule", "create", "permissions.alert_rule.create"),
        ("alert_rule", "update", "permissions.alert_rule.update"),
        ("alert_rule", "delete", "permissions.alert_rule.delete"),
        ("incident", "create", "permissions.incident.create"),
        ("incident", "acknowledge", "permissions.incident.acknowledge"),
        ("incident", "resolve", "permissions.incident.resolve"),
```
(Keep `("alert_rule", "read", ...)` and `("incident", "read", ...)` and retitle their section comments to `# ── Alert rules (ACCOUNT-level: available-alerts route only) ──` and `# ── Incidents (GLOBAL: cross-project list route only) ──`.)

Append a new section at the end of `CATALOG`:

```python
        # ── PROJECT-SCOPED twins ───────────────────────────────────
        # Distinct resource strings, not aliases. These are the ONLY
        # resources ProjectScopedPermissionCatalog.ASSIGNABLE may ever
        # contain. Their account-level namesakes above stay reachable only
        # through a real cloudflare_account_managers grant (the
        # account-manager path of require_cloudflare_environment_access),
        # so a project role can never mint account-level power — the
        # escalation loop a shared resource string left open.
        ("project_cloudflare_config", "read", "permissions.project_cloudflare_config.read"),
        ("project_cloudflare_dns", "read", "permissions.project_cloudflare_dns.read"),
        ("project_cloudflare_dns", "create", "permissions.project_cloudflare_dns.create"),
        ("project_cloudflare_dns", "update", "permissions.project_cloudflare_dns.update"),
        ("project_cloudflare_dns", "delete", "permissions.project_cloudflare_dns.delete"),
        # No project_cloudflare_tunnel.delete / .reveal_token, ever: a tunnel
        # is an ACCOUNT-wide object commonly serving several unrelated
        # projects at once (CloudflareTunnel has no environment_id column at
        # all), so deleting one or revealing its live connector token is an
        # account-tier action no project role may hold.
        ("project_cloudflare_tunnel", "read", "permissions.project_cloudflare_tunnel.read"),
        ("project_cloudflare_tunnel", "create", "permissions.project_cloudflare_tunnel.create"),
        ("project_cloudflare_tunnel", "sync", "permissions.project_cloudflare_tunnel.sync"),
        (
            "project_cloudflare_tunnel",
            "refresh_status",
            "permissions.project_cloudflare_tunnel.refresh_status",
        ),
        ("project_cloudflare_hostname", "read", "permissions.project_cloudflare_hostname.read"),
        ("project_cloudflare_hostname", "create", "permissions.project_cloudflare_hostname.create"),
        ("project_cloudflare_hostname", "update", "permissions.project_cloudflare_hostname.update"),
        ("project_cloudflare_hostname", "delete", "permissions.project_cloudflare_hostname.delete"),
        ("project_cloudflare_audit", "read", "permissions.project_cloudflare_audit.read"),
        ("project_loki_config", "read", "permissions.project_loki_config.read"),
        ("project_loki_config", "manage", "permissions.project_loki_config.manage"),
        ("project_alert_rule", "create", "permissions.project_alert_rule.create"),
        ("project_alert_rule", "read", "permissions.project_alert_rule.read"),
        ("project_alert_rule", "update", "permissions.project_alert_rule.update"),
        ("project_alert_rule", "delete", "permissions.project_alert_rule.delete"),
        ("project_incident", "create", "permissions.project_incident.create"),
        ("project_incident", "read", "permissions.project_incident.read"),
        ("project_incident", "acknowledge", "permissions.project_incident.acknowledge"),
        ("project_incident", "resolve", "permissions.project_incident.resolve"),
```

In `RbacResources`, delete `LOKI_CONFIG = "loki_config"` and append:

```python
    PROJECT_CLOUDFLARE_CONFIG = "project_cloudflare_config"
    PROJECT_CLOUDFLARE_TUNNEL = "project_cloudflare_tunnel"
    PROJECT_CLOUDFLARE_HOSTNAME = "project_cloudflare_hostname"
    PROJECT_CLOUDFLARE_DNS = "project_cloudflare_dns"
    PROJECT_CLOUDFLARE_AUDIT = "project_cloudflare_audit"
    PROJECT_LOKI_CONFIG = "project_loki_config"
    PROJECT_ALERT_RULE = "project_alert_rule"
    PROJECT_INCIDENT = "project_incident"
```

- [ ] **Step 4:** `cd backend && uv run pytest tests/rbac/test_constants.py -v` → PASS. (`app/modules/observability/router.py` will not import — expected; Task 7 fixes it.)

- [ ] **Step 5: Commit** — `feat(rbac): split project-scoped permission resources from their account-level namesakes`

---

## Task 2: Rewrite `ProjectScopedPermissionCatalog.ASSIGNABLE` onto the new names

**Files:**
- Modify: `backend/app/modules/projects/constants.py:81-141`
- Test: `backend/tests/projects/test_rules.py`

- [ ] **Step 1: Write the failing test**

Replace `TestAssignableKeys` in `backend/tests/projects/test_rules.py`:

```python
class TestAssignableKeys:
    def test_includes_environment_update_but_not_project_delete(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("environment", "update") in keys
        assert ("project", "delete") not in keys
        assert ("project", "manage_all") not in keys
        assert ("project_member", "manage") not in keys
        assert ("project_role", "read") not in keys
        assert ("project_role", "manage") not in keys
        assert ("user", "update_status") not in keys

    def test_only_project_prefixed_cloudflare_and_observability_atoms(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("project_cloudflare_dns", "create") in keys
        assert ("project_cloudflare_tunnel", "create") in keys
        assert ("project_cloudflare_hostname", "update") in keys
        assert ("project_cloudflare_config", "read") in keys
        assert ("project_cloudflare_audit", "read") in keys
        assert ("project_loki_config", "manage") in keys
        assert ("project_alert_rule", "create") in keys
        assert ("project_incident", "acknowledge") in keys

    def test_no_account_level_resource_is_assignable_under_its_old_name(self) -> None:
        """Regression guard for the exact escalation this split closes: an
        account-level resource string must NEVER re-enter ASSIGNABLE."""
        account_level = {
            "cloudflare_account", "cloudflare_manager", "cloudflare_config",
            "cloudflare_tunnel", "cloudflare_hostname", "cloudflare_dns",
            "cloudflare_audit", "loki_config", "alert_rule", "incident",
        }
        offenders = [k for k in ProjectRoleRules.assignable_keys() if k[0] in account_level]
        assert offenders == []

    def test_tunnel_delete_and_reveal_token_are_unassignable_under_any_name(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("cloudflare_tunnel", "delete") not in keys
        assert ("cloudflare_tunnel", "reveal_token") not in keys
        assert ("project_cloudflare_tunnel", "delete") not in keys
        assert ("project_cloudflare_tunnel", "reveal_token") not in keys

    def test_every_assignable_key_exists_in_the_rbac_catalog(self) -> None:
        """A tuple in ASSIGNABLE with no matching CATALOG row can never be
        granted (no Permission id exists) — a silent dead entry."""
        from app.modules.rbac.constants import RbacPermissionCatalog

        catalog = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ProjectRoleRules.assignable_keys() <= catalog
        assert len(ProjectRoleRules.assignable_keys()) == 33
```

- [ ] **Step 2:** `cd backend && uv run pytest tests/projects/test_rules.py -v` → FAIL.

- [ ] **Step 3: Implement** — replace `ProjectScopedPermissionCatalog` in `backend/app/modules/projects/constants.py`:

```python
class ProjectScopedPermissionCatalog:
    """The subset of the global rbac.Permission catalog a ProjectRole may
    ever grant.

    Every Cloudflare/Loki/Alerting/Incident entry below is a `project_`-
    prefixed resource whose ONLY check site is a project-scoped dependency.
    The account-level namesakes (cloudflare_tunnel.*, cloudflare_dns.*,
    loki_config.*, alert_rule.*, incident.*) are deliberately absent: they
    are what the account-manager path of require_cloudflare_environment_access
    checks, and letting a project role grant one of those strings is exactly
    the cross-tenant escalation this split closes. Before the split, a
    Project-A-only member with a role granting cloudflare_tunnel.delete could
    delete a tunnel actively serving Projects B/C/D, because a Cloudflare
    Tunnel is an ACCOUNT-wide object (CloudflareTunnel has no environment_id
    column at all — see cloudflare/models.py).

    Permanently excluded, in every namespace: project.delete (cascades every
    downstream Cloudflare/Loki/alerting row), project.manage_all,
    project_member.manage, both project_role.* atoms, all Cloudflare ACCOUNT
    administration (cloudflare_account.*, cloudflare_manager.*),
    cloudflare_config.manage (binding an environment to an account is a
    trust-establishing action — a project role may only OPERATE inside a
    binding someone with real account access already established), and —
    added by this split — cloudflare_tunnel.delete and
    cloudflare_tunnel.reveal_token, which have no project_ twin at all.

    See docs/superpowers/plans/2026-08-26-project-scoped-resource-split-and-
    tunnel-hostname-ownership-fix.md."""

    ASSIGNABLE: frozenset[tuple[str, str]] = frozenset(
        {
            ("project", "read"),
            ("project", "update"),
            ("environment", "create"),
            ("environment", "read"),
            ("environment", "update"),
            ("environment", "delete"),
            ("project_link", "read"),
            ("project_link", "manage"),
            ("project_member", "read"),
            ("project_cloudflare_config", "read"),
            ("project_cloudflare_dns", "read"),
            ("project_cloudflare_dns", "create"),
            ("project_cloudflare_dns", "update"),
            ("project_cloudflare_dns", "delete"),
            ("project_cloudflare_tunnel", "read"),
            ("project_cloudflare_tunnel", "create"),
            ("project_cloudflare_tunnel", "sync"),
            ("project_cloudflare_tunnel", "refresh_status"),
            ("project_cloudflare_hostname", "read"),
            ("project_cloudflare_hostname", "create"),
            ("project_cloudflare_hostname", "update"),
            ("project_cloudflare_hostname", "delete"),
            ("project_cloudflare_audit", "read"),
            ("project_loki_config", "read"),
            ("project_loki_config", "manage"),
            ("project_alert_rule", "create"),
            ("project_alert_rule", "read"),
            ("project_alert_rule", "update"),
            ("project_alert_rule", "delete"),
            ("project_incident", "create"),
            ("project_incident", "read"),
            ("project_incident", "acknowledge"),
            ("project_incident", "resolve"),
        }
    )
```

- [ ] **Step 4:** `cd backend && uv run pytest tests/projects/test_rules.py -v` → PASS.

- [ ] **Step 5: Commit** — `feat(projects): restrict ASSIGNABLE to project_-prefixed resources only`

---

## Task 3: Alembic data migration — split the rows, move the grants

**Files:**
- Create: `backend/alembic/versions/c5e1b8a47d92_split_project_scoped_permission_resources.py`

Head revision is `a3f7d9c2e5b1` (confirmed via `uv run alembic heads`).

- [ ] **Step 1: Write the migration**

```python
"""split_project_scoped_permission_resources

Revision ID: c5e1b8a47d92
Revises: a3f7d9c2e5b1
Create Date: 2026-08-26 09:00:00.000000

Eight resources were being checked under ONE resource string on two very
different authorization surfaces: the Cloudflare-account-manager surface
(a real cloudflare_account_managers grant) and the project-role surface
(membership in one project). Because ProjectScopedPermissionCatalog.
ASSIGNABLE listed those shared strings, a project role could grant
account-tier power — most severely cloudflare_tunnel.delete and
cloudflare_tunnel.reveal_token on a tunnel that is an ACCOUNT-wide object
commonly serving several unrelated projects at once.

This migration splits the catalog: each project-scoped surface gets its own
`project_`-prefixed resource, and the account-level names stay put. It then
moves existing grants so nobody silently loses a capability:

  * role_permissions (global roles): COPIED to the new name where the old
    name still guards a real account/global route (a global-permission
    holder passes today through resolve_effective_permissions' global-UNION
    half — the copy preserves that byte-for-byte), MOVED where the old row
    is being retired outright.
  * project_role_permissions: MOVED in every case — a project role holding
    an account-level string is precisely what the split forbids.
  * cloudflare_tunnel.delete / .reveal_token project-role grants: DELETED
    with no replacement. That is the security fix, and it is intentionally
    NOT reversible (see downgrade()).

Retired rows are deleted here rather than left to seed_rbac.py's
delete-if-not-in-CATALOG sweep, so the whole operation is atomic and the
seed has nothing left to strip.

ORDERING: run `alembic upgrade head` BEFORE `python -m app.seeds.seed_rbac`.
Running the seed first against the new CATALOG would delete the retired
rows (cascading role_permissions and project_role_permissions) before this
migration can move their grants. The companion guard added to seed_rbac.py
turns that into a loud refusal rather than silent loss, but the ordering is
still the supported path.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "c5e1b8a47d92"
down_revision = "a3f7d9c2e5b1"
branch_labels = None
depends_on = None


# (old_resource, new_resource, action): the new row is created and the OLD
# row SURVIVES, because some account-level or global route still checks it.
COPY_TO_NEW: list[tuple[str, str, str]] = [
    ("cloudflare_config", "project_cloudflare_config", "read"),
    ("cloudflare_dns", "project_cloudflare_dns", "read"),
    ("cloudflare_dns", "project_cloudflare_dns", "create"),
    ("cloudflare_dns", "project_cloudflare_dns", "update"),
    ("cloudflare_dns", "project_cloudflare_dns", "delete"),
    ("cloudflare_tunnel", "project_cloudflare_tunnel", "read"),
    ("cloudflare_tunnel", "project_cloudflare_tunnel", "create"),
    ("cloudflare_tunnel", "project_cloudflare_tunnel", "sync"),
    ("cloudflare_tunnel", "project_cloudflare_tunnel", "refresh_status"),
    ("cloudflare_hostname", "project_cloudflare_hostname", "read"),
    ("cloudflare_hostname", "project_cloudflare_hostname", "create"),
    ("cloudflare_hostname", "project_cloudflare_hostname", "update"),
    ("cloudflare_hostname", "project_cloudflare_hostname", "delete"),
    ("cloudflare_audit", "project_cloudflare_audit", "read"),
    ("alert_rule", "project_alert_rule", "read"),
    ("incident", "project_incident", "read"),
]

# (old_resource, new_resource, action): the new row is created and the OLD
# row is DELETED — no call site anywhere checks the old name any more.
MOVE_TO_NEW: list[tuple[str, str, str]] = [
    ("loki_config", "project_loki_config", "read"),
    ("loki_config", "project_loki_config", "manage"),
    ("alert_rule", "project_alert_rule", "create"),
    ("alert_rule", "project_alert_rule", "update"),
    ("alert_rule", "project_alert_rule", "delete"),
    ("incident", "project_incident", "create"),
    ("incident", "project_incident", "acknowledge"),
    ("incident", "project_incident", "resolve"),
]

# Atoms that stop being project-assignable with NO replacement.
REVOKED_FROM_PROJECT_ROLES: list[tuple[str, str]] = [
    ("cloudflare_tunnel", "delete"),
    ("cloudflare_tunnel", "reveal_token"),
]

_INSERT_PERMISSION = sa.text(
    """
    INSERT INTO permissions (id, resource, action, description_key)
    SELECT :new_id, :resource, :action, :description_key
    WHERE NOT EXISTS (
        SELECT 1 FROM permissions WHERE resource = :resource AND action = :action
    )
    """
)

_COPY_ROLE_GRANTS = sa.text(
    """
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT rp.role_id, new_p.id
    FROM role_permissions rp
    JOIN permissions old_p ON old_p.id = rp.permission_id
    JOIN permissions new_p ON new_p.resource = :new_resource AND new_p.action = :action
    WHERE old_p.resource = :old_resource AND old_p.action = :action
    ON CONFLICT DO NOTHING
    """
)

_COPY_PROJECT_ROLE_GRANTS = sa.text(
    """
    INSERT INTO project_role_permissions (project_role_id, permission_id)
    SELECT prp.project_role_id, new_p.id
    FROM project_role_permissions prp
    JOIN permissions old_p ON old_p.id = prp.permission_id
    JOIN permissions new_p ON new_p.resource = :new_resource AND new_p.action = :action
    WHERE old_p.resource = :old_resource AND old_p.action = :action
    ON CONFLICT DO NOTHING
    """
)

_DELETE_PROJECT_ROLE_GRANTS = sa.text(
    """
    DELETE FROM project_role_permissions
    WHERE permission_id IN (
        SELECT id FROM permissions WHERE resource = :resource AND action = :action
    )
    """
)

_DELETE_PERMISSION = sa.text(
    "DELETE FROM permissions WHERE resource = :resource AND action = :action"
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create every new project_-prefixed permission row.
    for _old_resource, new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        bind.execute(
            _INSERT_PERMISSION,
            {
                "new_id": uuid.uuid4(),
                "resource": new_resource,
                "action": action,
                "description_key": f"permissions.{new_resource}.{action}",
            },
        )

    # 2. Propagate grants BEFORE anything is deleted.
    for old_resource, new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        params = {"old_resource": old_resource, "new_resource": new_resource, "action": action}
        bind.execute(_COPY_ROLE_GRANTS, params)
        bind.execute(_COPY_PROJECT_ROLE_GRANTS, params)

    # 3. A project role must never hold an ACCOUNT-level resource string:
    #    drop the now-superseded project-role grants on the old names.
    for old_resource, _new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        bind.execute(_DELETE_PROJECT_ROLE_GRANTS, {"resource": old_resource, "action": action})

    # 4. The security fix proper — these two have no project_ twin to move to.
    for resource, action in REVOKED_FROM_PROJECT_ROLES:
        bind.execute(_DELETE_PROJECT_ROLE_GRANTS, {"resource": resource, "action": action})

    # 5. Retire the old rows whose every call site became project-scoped.
    #    role_permissions rows cascade (FK ondelete=CASCADE) — that is what
    #    MOVE means, and step 2 already re-granted the new name.
    for old_resource, _new_resource, action in MOVE_TO_NEW:
        bind.execute(_DELETE_PERMISSION, {"resource": old_resource, "action": action})


def downgrade() -> None:
    """Restores the retired account-level rows and their grants.

    NOT restored: project_role_permissions grants on cloudflare_tunnel.delete
    and cloudflare_tunnel.reveal_token. Those were deleted as a security fix
    and the pre-fix state is deliberately unrecoverable, mirroring
    a2f7c391e05d's own 'historical intent is unrecoverable' precedent. A
    downgraded database simply has those project roles without those two
    atoms — re-add them by hand only if you consciously want the escalation
    back.
    """
    bind = op.get_bind()

    # 1. Recreate the retired old rows.
    for old_resource, _new_resource, action in MOVE_TO_NEW:
        bind.execute(
            _INSERT_PERMISSION,
            {
                "new_id": uuid.uuid4(),
                "resource": old_resource,
                "action": action,
                "description_key": f"permissions.{old_resource}.{action}",
            },
        )

    # 2. Copy grants back, new -> old (arguments swapped).
    for old_resource, new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        params = {"old_resource": new_resource, "new_resource": old_resource, "action": action}
        bind.execute(_COPY_ROLE_GRANTS, params)
        bind.execute(_COPY_PROJECT_ROLE_GRANTS, params)

    # 3. Drop every project_-prefixed row; its grants cascade.
    for _old_resource, new_resource, action in COPY_TO_NEW + MOVE_TO_NEW:
        bind.execute(_DELETE_PERMISSION, {"resource": new_resource, "action": action})
```

- [ ] **Step 2: Verify against a throwaway database, never `itsm`**

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic upgrade head
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic downgrade -1
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5435/itsm_test" uv run alembic upgrade head
```
Expected: all three succeed. Then confirm by query that `permissions` contains 24 `project_%` rows and zero `loki_config` rows, and that a project role which held `cloudflare_tunnel.create` now holds `project_cloudflare_tunnel.create` and no longer holds `cloudflare_tunnel.create`.

- [ ] **Step 3: Commit** — `feat(rbac): data migration splitting project-scoped resources and moving grants`

---

## Task 4: Make `seed_rbac.py` refuse to strip a permission that is still granted

**Files:**
- Modify: `backend/app/seeds/seed_rbac.py:57-75`

This is the permanent guard behind the migration-ordering risk. Independent of this plan's migration, it converts "silently deletes every role's grants on a catalog rename" into a loud, safe refusal.

- [ ] **Step 1: Implement**

Replace the `# ── 2. Clean up stale permissions no longer in CATALOG ──` block:

```python
        # ── 2. Clean up stale permissions no longer in CATALOG ──────
        # A stale permission that NOTHING references is safe to drop. A
        # stale permission that a role (global or project) still grants is
        # NOT: deleting it cascades role_permissions AND
        # project_role_permissions (both FK ondelete=CASCADE), silently
        # stripping real capability from real roles. That is exactly how a
        # bare catalog rename destroys grants, so refuse and shout instead —
        # an accompanying Alembic data migration is the supported way to
        # retire a permission that is still in use.
        all_db_perms = list(await session.scalars(select(Permission)))
        stale_perms = [p for p in all_db_perms if (p.resource, p.action) not in catalog_keys]
        if stale_perms:
            stale_ids = [p.id for p in stale_perms]
            stale_links = list(
                await session.scalars(
                    select(RolePermission).where(RolePermission.permission_id.in_(stale_ids))
                )
            )
            granted_ids = {link.permission_id for link in stale_links}
            granted_project_ids = set(
                await session.scalars(
                    text(
                        "SELECT permission_id FROM project_role_permissions "
                        "WHERE permission_id = ANY(:ids)"
                    ).bindparams(ids=stale_ids)
                )
            )
            blocked = granted_ids | granted_project_ids
            for perm in stale_perms:
                if perm.id in blocked:
                    logger.error(
                        "REFUSING to remove permission %s.%s — roles still grant it. Write an "
                        "Alembic data migration that moves those grants first, then re-run this "
                        "seed. Nothing was deleted for this permission.",
                        perm.resource,
                        perm.action,
                    )
            for link in stale_links:
                if link.permission_id not in blocked:
                    await session.delete(link)
            for perm in stale_perms:
                if perm.id in blocked:
                    continue
                logger.info("removing stale permission %s.%s", perm.resource, perm.action)
                await session.delete(perm)
            await session.flush()
        await session.commit()
```

Add `text` to the existing `from sqlalchemy import select` import: `from sqlalchemy import select, text`.

> Note: the raw `text(...)` query is deliberate — `project_role_permissions` is owned by the projects module, and `seed_rbac.py` must not import `app.modules.projects.models` (module-boundary rule). A seed script reading one column by raw SQL is the smallest possible exception and is documented as such in the comment above.

- [ ] **Step 2: Verify**

Temporarily comment out one `CATALOG` line that a role definitely holds, run the seed against `itsm_test`, confirm the `REFUSING to remove permission …` error is logged and the row + its grants still exist. Restore the line.

- [ ] **Step 3: Commit** — `fix(seeds): never silently strip a still-granted permission on catalog change`

---

## Task 5: Teach `require_cloudflare_environment_access` two resource names

**Files:**
- Modify: `backend/app/modules/cloudflare/dependencies.py:121-175`
- Test: `backend/tests/cloudflare/test_dependencies.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/cloudflare/test_dependencies.py`, update the three existing `require_cloudflare_environment_access` tests to the new signature and add three new ones (rename the fixture/helper classes to match whatever is already in that file — read it first):

```python
async def test_require_cloudflare_environment_access_existing_account_manager_path_unchanged() -> None:
    """A user who already passes today's check (global permission + account-
    manager row) must still succeed via the FIRST branch, checking the
    ACCOUNT-level resource name — proves the split changed nothing for them."""
    account_id = uuid4()
    check = require_cloudflare_environment_access(
        "cloudflare_dns", "project_cloudflare_dns", "create", AccessLevel.EDITOR
    )
    grant = await check(
        environment_id=uuid4(),
        auth_api=FakeAuthApi(_FAKE_USER),
        rbac_api=FakeRbacApi(manage_all=False, global_permissions=["cloudflare_dns.create"]),
        uow=FakeUowWithConfigs(account_manager_row_at(AccessLevel.EDITOR), account_id),
        projects_api=FakeProjectsApi(),  # never consulted on this path
    )
    assert grant.held_level is AccessLevel.EDITOR


async def test_project_path_checks_the_project_prefixed_name_only() -> None:
    environment_id = uuid4()
    check = require_cloudflare_environment_access(
        "cloudflare_dns", "project_cloudflare_dns", "create", AccessLevel.EDITOR
    )
    grant = await check(
        environment_id=environment_id,
        auth_api=FakeAuthApi(_FAKE_USER),
        rbac_api=FakeRbacApi(manage_all=False, global_permissions=[]),
        uow=FakeUowWithConfigs(None, uuid4()),
        projects_api=FakeProjectsApi(
            environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
            permissions=frozenset({"project_cloudflare_dns.create"}),
        ),
    )
    assert grant.held_level is None


async def test_account_level_name_in_the_project_set_is_NOT_accepted() -> None:
    """The escalation regression test: holding the OLD account-level string
    in a project-scoped effective set must never satisfy the project path."""
    environment_id = uuid4()
    check = require_cloudflare_environment_access(
        "cloudflare_dns", "project_cloudflare_dns", "create", AccessLevel.EDITOR
    )
    with pytest.raises(InsufficientAccountAccess):
        await check(
            environment_id=environment_id,
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False, global_permissions=[]),
            uow=FakeUowWithConfigs(None, uuid4()),
            projects_api=FakeProjectsApi(
                environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
                permissions=frozenset({"cloudflare_dns.create"}),
            ),
        )


async def test_project_resource_none_skips_the_project_path_entirely() -> None:
    """cloudflare_tunnel.delete / .reveal_token: no project name exists, so
    no project-scoped grant of any shape can satisfy the route."""
    environment_id = uuid4()
    check = require_cloudflare_environment_access(
        "cloudflare_tunnel", None, "delete", AccessLevel.EDITOR
    )
    with pytest.raises(InsufficientAccountAccess):
        await check(
            environment_id=environment_id,
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False, global_permissions=[]),
            uow=FakeUowWithConfigs(None, uuid4()),
            projects_api=FakeProjectsApi(
                environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
                permissions=frozenset(
                    {"cloudflare_tunnel.delete", "project_cloudflare_tunnel.delete"}
                ),
            ),
        )


async def test_require_cloudflare_environment_access_raises_when_both_paths_fail() -> None:
    environment_id = uuid4()
    check = require_cloudflare_environment_access(
        "cloudflare_dns", "project_cloudflare_dns", "create", AccessLevel.EDITOR
    )
    with pytest.raises(InsufficientAccountAccess):
        await check(
            environment_id=environment_id,
            auth_api=FakeAuthApi(_FAKE_USER),
            rbac_api=FakeRbacApi(manage_all=False, global_permissions=[]),
            uow=FakeUowWithConfigs(None, uuid4()),
            projects_api=FakeProjectsApi(
                environment=_FakeEnvironment(id=environment_id, project_id=uuid4()),
                permissions=frozenset(),
            ),
        )
```

- [ ] **Step 2:** `cd backend && uv run pytest tests/cloudflare/test_dependencies.py -v` → FAIL (TypeError on the 4-arg signature).

- [ ] **Step 3: Implement** — replace `require_cloudflare_environment_access` in `backend/app/modules/cloudflare/dependencies.py`:

```python
def require_cloudflare_environment_access(
    account_resource: str, project_resource: str | None, action: str, min_level: AccessLevel
):
    """Composed check for environment-scoped Cloudflare routes (DNS, Tunnel,
    hostnames, config-read, audit-log-read) — never used on account
    administration or binding/unbinding routes, which stay exclusively gated
    by require_account_access*/require_account_access_for_environment.

    The two paths check DIFFERENT resource strings, on purpose:

      * account-manager path (tried FIRST): global `account_resource.action`
        permission AND a sufficient cloudflare_account_managers level (or
        cloudflare_account:manage_all). Byte-for-byte today's combined
        Layer-1+Layer-2 behavior, same queries, same success shape, for
        every user who already passes it.
      * project-role path (fallback, only on InsufficientAccountAccess):
        `project_resource.action` in the caller's effective project-scoped
        permission set (global UNION project role) for the environment's
        project.

    Sharing ONE resource string across both paths is what let a project role
    grant account-tier Cloudflare power — most severely deleting or
    revealing the token of a tunnel serving several unrelated projects, since
    a Cloudflare Tunnel is an account-wide object with no environment_id at
    all. Distinct names make that structurally impossible: only
    `project_`-prefixed strings appear in ProjectScopedPermissionCatalog.
    ASSIGNABLE, so no project role can ever hold an `account_resource`.

    project_resource=None means the route has NO project-scoped path at all
    (cloudflare_tunnel.delete, cloudflare_tunnel.reveal_token): the fallback
    branch is skipped entirely, and genuine Cloudflare account access is the
    only way through. It is a required positional argument precisely so every
    call site has to state which of the two it is.

    held_level=None on the returned grant signals 'bypassed via a mechanism
    other than a literal cloudflare_account_managers row' — the same signal
    cloudflare_account:manage_all already uses, so any code inspecting
    held_level treats the two identically.

    Note (pre-existing, unchanged): resolve_effective_permissions raises
    InsufficientProjectAccess for a non-member, so a non-member sees that
    error code rather than InsufficientAccountAccess. That asymmetry predates
    this split and is preserved rather than silently re-coded."""

    async def check(
        environment_id: UUID,
        auth_api: AuthApi = Depends(get_auth_api),
        rbac_api: RbacApi = Depends(get_rbac_api),
        uow: AbstractCloudflareUnitOfWork = Depends(get_uow),
        projects_api: ProjectsApi = Depends(get_projects_api),
    ) -> AccountAccessGrant:
        user = auth_api.current_user()
        config = await uow.configs.get_by_environment_id(environment_id)
        if config is None:
            raise CloudflareConfigNotFound()

        if await rbac_api.has_permission(user.id, account_resource, action):
            try:
                return await resolve_account_access_grant(
                    config.cloudflare_account_id, user, rbac_api, uow, min_level
                )
            except InsufficientAccountAccess:
                pass

        if project_resource is not None:
            environment = await projects_api.get_environment_by_id(environment_id)
            if environment is not None:
                permissions = await projects_api.resolve_effective_permissions(
                    environment.project_id, user, rbac_api
                )
                if f"{project_resource}.{action}" in permissions:
                    return AccountAccessGrant(user=user, held_level=None)

        raise InsufficientAccountAccess()

    return check
```

- [ ] **Step 4:** `cd backend && uv run pytest tests/cloudflare/test_dependencies.py -v` → PASS.

- [ ] **Step 5: Commit** — `feat(cloudflare): check distinct account vs project resource names per path`

---

## Task 6: Update all 17 `require_cloudflare_environment_access` call sites

**Files:**
- Modify: `backend/app/modules/cloudflare/router.py`

- [ ] **Step 1: Apply this table** (re-verify each line number against the current file before editing — it may have shifted since this plan was written)

| Route | `account_resource` | `project_resource` | action / level |
|---|---|---|---|
| `GET /environments/{id}/cloudflare-config` | `CLOUDFLARE_CONFIG` | `PROJECT_CLOUDFLARE_CONFIG` | READ / VIEWER |
| `GET /environments/{id}/dns-records` | `CLOUDFLARE_DNS` | `PROJECT_CLOUDFLARE_DNS` | READ / VIEWER |
| `POST /environments/{id}/dns-records/sync` | `CLOUDFLARE_DNS` | `PROJECT_CLOUDFLARE_DNS` | READ / VIEWER |
| `GET /environments/{id}/cloudflare-audit-logs` | `CLOUDFLARE_AUDIT` | `PROJECT_CLOUDFLARE_AUDIT` | READ / VIEWER |
| `POST /environments/{id}/dns-records` | `CLOUDFLARE_DNS` | `PROJECT_CLOUDFLARE_DNS` | CREATE / EDITOR |
| `PATCH .../dns-records/{record_id}` | `CLOUDFLARE_DNS` | `PROJECT_CLOUDFLARE_DNS` | UPDATE / EDITOR |
| `DELETE .../dns-records/{record_id}` | `CLOUDFLARE_DNS` | `PROJECT_CLOUDFLARE_DNS` | DELETE / EDITOR |
| `GET /environments/{id}/cloudflare-tunnels` | `CLOUDFLARE_TUNNEL` | `PROJECT_CLOUDFLARE_TUNNEL` | READ / VIEWER |
| `POST .../cloudflare-tunnels/sync` | `CLOUDFLARE_TUNNEL` | `PROJECT_CLOUDFLARE_TUNNEL` | SYNC / EDITOR |
| `POST /environments/{id}/cloudflare-tunnels` | `CLOUDFLARE_TUNNEL` | `PROJECT_CLOUDFLARE_TUNNEL` | CREATE / EDITOR |
| **`DELETE .../cloudflare-tunnels/{tunnel_id}`** | `CLOUDFLARE_TUNNEL` | **`None`** | DELETE / EDITOR |
| **`POST .../{tunnel_id}/reveal-token`** | `CLOUDFLARE_TUNNEL` | **`None`** | REVEAL_TOKEN / EDITOR |
| `POST .../{tunnel_id}/refresh-status` | `CLOUDFLARE_TUNNEL` | `PROJECT_CLOUDFLARE_TUNNEL` | REFRESH_STATUS / EDITOR |
| `GET .../{tunnel_id}/hostnames` | `CLOUDFLARE_HOSTNAME` | `PROJECT_CLOUDFLARE_HOSTNAME` | READ / VIEWER |
| `POST .../{tunnel_id}/hostnames` | `CLOUDFLARE_HOSTNAME` | `PROJECT_CLOUDFLARE_HOSTNAME` | CREATE / EDITOR |
| `PATCH .../hostnames/{hostname_id}` | `CLOUDFLARE_HOSTNAME` | `PROJECT_CLOUDFLARE_HOSTNAME` | UPDATE / EDITOR |
| `DELETE .../hostnames/{hostname_id}` | `CLOUDFLARE_HOSTNAME` | `PROJECT_CLOUDFLARE_HOSTNAME` | DELETE / EDITOR |

Unchanged, deliberately: `require_permission(RbacResources.CLOUDFLARE_CONFIG, RbacActions.READ)` on the account-level zone picker (already stacked with `require_account_access(VIEWER)`), every `require_permission(CLOUDFLARE_CONFIG, MANAGE)` on bind/rebind/unbind, and every `require_account_access*` call site.

For the two `None` routes, add a docstring explaining why, e.g.:

```python
@router.delete("/environments/{environment_id}/cloudflare-tunnels/{tunnel_id}")
async def delete_environment_tunnel(
    environment_id: UUID,
    tunnel_id: UUID,
    use_case: DeleteCloudflareTunnel = Depends(get_delete_tunnel),
    grant: AccountAccessGrant = Depends(
        require_cloudflare_environment_access(
            RbacResources.CLOUDFLARE_TUNNEL, None, RbacActions.DELETE, AccessLevel.EDITOR
        )
    ),
) -> ApiResponse[None]:
    """Delete a tunnel. Its public hostnames cascade at the DB level.

    project_resource=None: a Cloudflare Tunnel is an ACCOUNT-wide object that
    commonly serves several unrelated projects at once (CloudflareTunnel has
    no environment_id column at all), so deleting one from inside a single
    project would silently take down every other project it serves. Genuine
    cloudflare_account_managers access is the only way through; no project
    role can grant it."""
```

- [ ] **Step 2: Update the router module docstring** — add a paragraph explaining the two-name convention.

- [ ] **Step 3:** `cd backend && uv run pytest tests/cloudflare/ -q` — the pre-existing router tests that grant `("cloudflare_tunnel", "create")` etc. to an actual account manager still pass (account-manager path is unchanged); `TestProjectRoleGrantsEnvironmentScopedCloudflareAccess` now FAILS because it grants the old `cloudflare_tunnel.create` to a project role. Update that test to use `project_cloudflare_tunnel` and add the negative assertion that granting the OLD `cloudflare_tunnel.create` string to a project role is itself rejected by the roles endpoint (422, `projects_permission_not_project_assignable` or whatever the actual current error code is — check `ProjectRoleRules`'s rejection path first).

- [ ] **Step 4: Commit** — `feat(cloudflare): route the project path through project_-prefixed resources; remove it from tunnel delete/reveal-token`

---

## Task 7: Point observability at the project-scoped resource names

**Files:**
- Modify: `backend/app/modules/observability/router.py`
- Modify: `backend/app/modules/observability/services/create_manual_incident.py`
- Test: `backend/tests/observability/test_dependencies.py`, `backend/tests/observability/test_router.py`

The three factories (`require_project_permission_for_environment` / `_for_alert_rule` / `_for_incident`) keep their `(resource, action)` signature — they are pure project-scoped checks with no account path, so one resource name is correct. Only the arguments change.

- [ ] **Step 1: Update the tests first**

In `backend/tests/observability/test_dependencies.py`, change every `require_project_permission_for_environment("loki_config", ...)`/`_for_alert_rule("alert_rule", ...)`/`_for_incident("incident", ...)` call to `"project_loki_config"`/`"project_alert_rule"`/`"project_incident"`, and the permission sets fed to the Fake projects API accordingly. Add one new test proving the OLD name no longer satisfies the check (mirrors the cloudflare regression test in Task 5).

In `backend/tests/observability/test_router.py`, update every `_login_with_permissions(..., permissions=[...])` tuple: `("loki_config", ...)` → `("project_loki_config", ...)`, `("alert_rule", "create"/"update"/"delete")` → `("project_alert_rule", ...)` (but `("alert_rule", "read")` used specifically for the `available-alerts` route test stays unchanged), `("incident", "create"/"acknowledge"/"resolve")` → `("project_incident", ...)` (but the `GET /incidents` list test's `("incident", "read")` stays unchanged). `("cloudflare_config", "manage")` on the binding-setup helper is unchanged.

- [ ] **Step 2:** `cd backend && uv run pytest tests/observability/ -q` → FAIL.

- [ ] **Step 3: Implement**

In `backend/app/modules/observability/router.py`: swap `RbacResources.LOKI_CONFIG` → `RbacResources.PROJECT_LOKI_CONFIG` on every Loki route; `RbacResources.ALERT_RULE` → `RbacResources.PROJECT_ALERT_RULE` on every environment/alert-rule-id-keyed route (leave the `available-alerts` route's `RbacResources.ALERT_RULE` unchanged); `RbacResources.INCIDENT` → `RbacResources.PROJECT_INCIDENT` on every id-keyed incident route (leave `GET /incidents`'s `RbacResources.INCIDENT` unchanged). Update the module docstring to state the convention (project_-prefixed for project-scoped routes; the two exceptions and why).

In `backend/app/modules/observability/services/create_manual_incident.py`, the permission check becomes:
```python
        if f"{RbacResources.PROJECT_INCIDENT}.{RbacActions.CREATE}" not in permissions:
```
Update the class docstring's reference from `incident.create` to `project_incident.create`.

- [ ] **Step 4:** `cd backend && uv run pytest tests/observability/ -q` → PASS.

- [ ] **Step 5: Commit** — `feat(observability): gate project-scoped routes on project_-prefixed resources`

---

## Task 8: Rename the misleading ownership rule and add the cross-environment claim rule

**Files:**
- Modify: `backend/app/modules/cloudflare/rules.py`
- Modify (call-site rename only): `services/{delete_tunnel,reveal_tunnel_token,refresh_tunnel_status,add_tunnel_hostname,update_tunnel_hostname,remove_tunnel_hostname,list_tunnel_hostnames}.py`
- Test: `backend/tests/cloudflare/test_rules.py`

`TunnelOwnershipRules.verify_tunnel_belongs_to_environment` does not check the environment at all — it compares `tunnel.cloudflare_account_id`. That misleading name is part of why the bug survived review. Rename it to say what it does.

- [ ] **Step 1: Write the failing tests** in `backend/tests/cloudflare/test_rules.py`:

```python
class TestTunnelOwnershipRules:
    def test_verify_tunnel_belongs_to_account_matches_on_account_id(self) -> None:
        account_id = uuid4()
        tunnel = CloudflareTunnelRead.model_construct(cloudflare_account_id=account_id)
        assert TunnelOwnershipRules.verify_tunnel_belongs_to_account(tunnel, account_id) is True
        assert TunnelOwnershipRules.verify_tunnel_belongs_to_account(tunnel, uuid4()) is False
        assert TunnelOwnershipRules.verify_tunnel_belongs_to_account(None, account_id) is False


class TestClaimsAnotherEnvironment:
    def test_hostname_matching_a_sibling_base_url_is_a_claim(self) -> None:
        mine, sibling = uuid4(), uuid4()
        candidates = [(mine, "https://a.example.com"), (sibling, "https://b.example.com")]
        assert (
            TunnelHostnameRules.claims_another_environment("b.example.com", mine, candidates) is True
        )

    def test_hostname_matching_my_own_base_url_is_not_a_claim(self) -> None:
        mine, sibling = uuid4(), uuid4()
        candidates = [(mine, "https://a.example.com"), (sibling, "https://b.example.com")]
        assert (
            TunnelHostnameRules.claims_another_environment("a.example.com", mine, candidates) is False
        )

    def test_hostname_matching_nobody_is_not_a_claim(self) -> None:
        """The routine create case: publishing api.example.com when base_url
        is app.example.com. Rejecting this would break normal usage."""
        mine, sibling = uuid4(), uuid4()
        candidates = [(mine, "https://a.example.com"), (sibling, "https://b.example.com")]
        assert (
            TunnelHostnameRules.claims_another_environment("api.example.com", mine, candidates)
            is False
        )

    def test_siblings_without_a_base_url_never_claim_anything(self) -> None:
        mine, sibling = uuid4(), uuid4()
        candidates = [(mine, None), (sibling, None)]
        assert (
            TunnelHostnameRules.claims_another_environment("x.example.com", mine, candidates) is False
        )
```

- [ ] **Step 2:** `cd backend && uv run pytest tests/cloudflare/test_rules.py -v` → FAIL.

- [ ] **Step 3: Implement** — in `backend/app/modules/cloudflare/rules.py`, append to `TunnelHostnameRules`:

```python
    @staticmethod
    @rule
    def claims_another_environment(
        hostname: str, environment_id: UUID, candidates: list[tuple[UUID, str | None]]
    ) -> bool:
        """True when `hostname` is exactly the base_url host of a DIFFERENT
        environment among `candidates` (every environment bound to the same
        Cloudflare account). Built on match_environment_id so create-time
        rejection and sync-time attribution can never disagree.

        A hostname matching NO candidate is deliberately not a claim: an
        environment routinely publishes hostnames other than its own
        base_url (api.x.com alongside app.x.com), and rejecting those would
        break the normal create flow while blocking nothing — an unmatched
        hostname belongs to whoever creates it, which is exactly how
        AddTunnelHostname already attributes it. Only a positive match on
        somebody ELSE's base_url is a cross-environment takeover, and that
        is what this blocks."""
        matched = TunnelHostnameRules.match_environment_id(hostname, candidates)
        return matched is not None and matched != environment_id
```

and rewrite `TunnelOwnershipRules`:

```python
class TunnelOwnershipRules:
    """Pure decision rules for whether a Tunnel belongs to the Cloudflare
    ACCOUNT an environment is bound to. Deliberately account-level and
    named for it: a tunnel is an account-scoped object with no
    environment_id column, and many environments on one account may
    legitimately manage the same tunnel's hostnames. Per-ENVIRONMENT
    ownership lives one level down, on TunnelPublicHostname.environment_id —
    see the `existing.environment_id != environment_id` guards in
    update_tunnel_hostname/remove_tunnel_hostname and
    TunnelHostnameRules.claims_another_environment for create."""

    @staticmethod
    @rule
    def verify_tunnel_belongs_to_account(
        tunnel: CloudflareTunnelRead | None, cloudflare_account_id: UUID
    ) -> bool:
        """True iff tunnel exists and is on the given Cloudflare account.
        This is an ACCOUNT check, not an environment check — the previous
        name (verify_tunnel_belongs_to_environment) said otherwise and is
        why six write use cases looked environment-scoped while enforcing
        nothing of the kind."""
        return tunnel is not None and tunnel.cloudflare_account_id == cloudflare_account_id
```

Then update the 7 call sites (mechanical rename, no logic change) in `delete_tunnel.py`, `reveal_tunnel_token.py`, `refresh_tunnel_status.py`, `add_tunnel_hostname.py`, `update_tunnel_hostname.py`, `remove_tunnel_hostname.py`, `list_tunnel_hostnames.py`.

- [ ] **Step 4:** `cd backend && uv run pytest tests/cloudflare/ -q` → PASS (update any test in `tests/cloudflare/test_services.py` referencing the old name).

- [ ] **Step 5: Commit** — `refactor(cloudflare): name the tunnel ownership rule for what it checks; add cross-environment claim rule`

---

## Task 9: New exception for a hostname claimed by another environment

**Files:**
- Modify: `backend/app/modules/cloudflare/constants.py` (`ErrorCode`)
- Modify: `backend/app/modules/cloudflare/exceptions.py`

Check every existing exception class first. `TunnelHostnameDomainMismatch` is about the **zone**, `CloudflareTunnelNotFound`/`TunnelPublicHostnameNotFound` are 404s about missing rows. None fits "this hostname is another environment's" — a new `ValidationFailedError` mirroring `TunnelHostnameDomainMismatch`'s shape is correct.

- [ ] **Step 1: Implement**

`constants.py`, in `ErrorCode`:
```python
    TUNNEL_HOSTNAME_ENVIRONMENT_MISMATCH = "cloudflare_tunnel_hostname_environment_mismatch"
```

`exceptions.py`:
```python
class TunnelHostnameEnvironmentMismatch(ValidationFailedError):
    """Raised when the submitted hostname is exactly the base_url host of a
    DIFFERENT environment bound to the same Cloudflare account.

    TunnelHostnameDomainMismatch checks the ZONE, which is not enough:
    two environments belonging to two unrelated projects commonly share one
    zone on one account, so the zone check alone let Project A publish (and
    thereby hijack) a hostname belonging to Project B on the shared tunnel.
    This is the environment-level half of that guard — the Tunnel analogue
    of the `existing.environment_id != environment_id` check DNS records
    have enforced since the DNS environment-scoping fix."""

    code = ErrorCode.TUNNEL_HOSTNAME_ENVIRONMENT_MISMATCH
    message = "This hostname belongs to a different environment on the same Cloudflare account"
```

- [ ] **Step 2: Commit** — `feat(cloudflare): TunnelHostnameEnvironmentMismatch error`

---

## Task 10: Add the missing environment guard to hostname update + delete

**Files:**
- Modify: `backend/app/modules/cloudflare/services/update_tunnel_hostname.py`
- Modify: `backend/app/modules/cloudflare/services/remove_tunnel_hostname.py`
- Test: `backend/tests/cloudflare/test_services.py`

- [ ] **Step 1: Write the failing tests** — add to the tunnel-hostname section of `backend/tests/cloudflare/test_services.py`, matching the file's existing Fake-UoW fixtures (read the neighbouring `UpdateTunnelHostname`/`RemoveTunnelHostname` tests first, and reuse their setup helpers):
  - `test_update_rejects_a_hostname_owned_by_another_environment` — asserts `TunnelPublicHostnameNotFound` and that nothing reached Cloudflare (`client.put_calls == []`).
  - `test_update_rejects_an_unattributed_hostname` — `environment_id IS NULL` also rejected.
  - `test_remove_rejects_a_hostname_owned_by_another_environment`.

- [ ] **Step 2:** run → FAIL (both currently succeed and issue a Cloudflare PUT/DELETE).

- [ ] **Step 3: Implement**

In `update_tunnel_hostname.py`, replace the existing ownership check:
```python
        existing = await self._uow.tunnel_hostnames.get_by_id(hostname_id)
        if (
            existing is None
            or existing.tunnel_id != tunnel_id
            or existing.environment_id != environment_id
        ):
            # environment_id equality, not just tunnel_id: a tunnel is
            # ACCOUNT-scoped and commonly serves several unrelated projects
            # at once, so `belongs to this tunnel` proves nothing about
            # ownership. Mirrors UpdateDnsRecord's identical guard. NULL is
            # rejected too — an unattributed hostname belongs to no
            # environment and is already hidden from every environment's
            # list by ListTunnelHostnames' own environment_id filter.
            raise TunnelPublicHostnameNotFound()
```

Same change in `remove_tunnel_hostname.py` (mirroring `DeleteDnsRecord`'s guard). Update both module docstrings to record the guard.

- [ ] **Step 4:** run → PASS.

- [ ] **Step 5: Commit** — `fix(cloudflare): reject hostname update/delete across environment boundaries`

---

## Task 11: Reject creating a hostname that belongs to another environment

**Files:**
- Modify: `backend/app/modules/cloudflare/services/add_tunnel_hostname.py`
- Modify: `backend/app/modules/cloudflare/dependencies.py` (`get_add_tunnel_hostname`)
- Test: `backend/tests/cloudflare/test_services.py`

- [ ] **Step 1: Write the failing tests**
  - `test_create_rejects_a_hostname_that_is_another_environments_base_url` — environments A and B share one account AND zone; B's `base_url` is `https://b.example.com`; creating that hostname from A raises `TunnelHostnameEnvironmentMismatch`, `client.put_calls == []`.
  - `test_create_allows_a_hostname_no_sibling_claims` — `api.example.com` (nobody's base_url) succeeds, attributed to the creating environment.
  - `test_create_allows_my_own_base_url` — succeeds.

  The Fake `ProjectsApi` needs `get_environment_by_id` returning an object with `.id` and `.base_url` — reuse the shape already used by `SyncTunnels`'s existing tests in this same file.

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3: Implement**

`add_tunnel_hostname.py`: add `projects_api: ProjectsApi` to the constructor. Immediately after the existing duplicate-hostname/zone check and before the lock is acquired:

```python
        # A tunnel is ACCOUNT-scoped, so belongs_to_zone above is not enough:
        # two environments of two unrelated projects commonly share one zone
        # on one account, and without this a Project-A member could publish
        # (and thereby hijack) a hostname that is Project B's own base_url on
        # the shared tunnel. Reuses the same pure matcher SyncTunnels uses to
        # ATTRIBUTE hostnames, so create-time rejection and sync-time
        # attribution can never disagree.
        candidates = await self._resolve_sibling_environments(config.cloudflare_account_id)
        if TunnelHostnameRules.claims_another_environment(hostname, environment_id, candidates):
            raise TunnelHostnameEnvironmentMismatch()
```

Add the helper (a deliberate small twin of `SyncTunnels._resolve_sibling_environments` — use cases own their helpers in this codebase rather than sharing them across use cases):

```python
    @helper
    async def _resolve_sibling_environments(
        self, cloudflare_account_id: UUID
    ) -> list[tuple[UUID, str | None]]:
        """Every environment bound to this Cloudflare account, paired with
        its base_url — the candidate pool
        TunnelHostnameRules.claims_another_environment matches against."""
        sibling_ids = await self._uow.configs.list_environment_ids_for_account(cloudflare_account_id)
        candidates: list[tuple[UUID, str | None]] = []
        for sibling_id in sibling_ids:
            sibling = await self._projects_api.get_environment_by_id(sibling_id)
            if sibling is not None:
                candidates.append((sibling.id, sibling.base_url))
        return candidates
```

`dependencies.py`'s `get_add_tunnel_hostname` gains `projects_api: ProjectsApi = Depends(get_projects_api)` and passes it through.

- [ ] **Step 4:** `cd backend && uv run pytest tests/cloudflare/ -q && uv run lint-imports` → PASS (confirms the `projects-facade` contract still holds — `app.modules.cloudflare` importing `projects.public` is already the established pattern, e.g. `SyncTunnels`).

- [ ] **Step 5: Commit** — `fix(cloudflare): reject creating a hostname that belongs to a sibling environment`

---

## Task 12: The decisive end-to-end proof

**Files:**
- Modify: `backend/tests/cloudflare/test_router.py`

- [ ] **Step 1: Write the test class** (reuse the file's existing `FakeCloudflareClient`, `_login_with_permissions`, `_switch_to` helpers)

Two projects, ONE shared Cloudflare account + zone, one shared tunnel created from env A, a hostname on it created for env B (matching B's `base_url`). A collaborator who is ONLY a member of Project A, holding a project role granting every still-project-assignable tunnel/hostname atom, with NO `cloudflare_account_managers` row and NO global Cloudflare permission:

- MUST be blocked (403/404/422, and `cf_client.put_calls`/`deleted_tunnel_ids` stay empty throughout):
  1. `DELETE .../cloudflare-tunnels/{tunnel_id}` → 403 `cloudflare_insufficient_account_access`
  2. `POST .../{tunnel_id}/reveal-token` → 403, token never appears in the response body
  3. `PATCH .../hostnames/{hostname_b_id}` (env B's hostname, reached through env A) → 404 `cloudflare_tunnel_hostname_not_found`
  4. `DELETE .../hostnames/{hostname_b_id}` → 404
  5. `POST .../hostnames` with `hostname: "b.example.com"` (claiming B's own base_url from env A) → 422 `cloudflare_tunnel_hostname_environment_mismatch`
- MUST still work (not a blanket lockout): creating a hostname matching env A's own base_url, and `POST .../refresh-status`.

Add a second test in the same class: a genuine `cloudflare_account_managers` EDITOR keeps every capability unchanged — can still delete the tunnel, reveal its token, and edit env B's hostname (through env B, the environment that actually owns it — the guard is an ownership boundary, not a permission tier, so even an account owner reaches a hostname only through its own environment).

Before running: confirm the environment-create body's `base_url` field name and `TunnelPublicHostnameRead`'s exact response shape against the current schemas — read them, don't guess.

- [ ] **Step 2:** `cd backend && uv run pytest tests/cloudflare/test_router.py -k "ConfinedToTheirOwnEnvironment or real_account_manager" -v` → PASS. If Tasks 1-11 are done correctly, this passes immediately; a failure here means an earlier task has a real bug, not a test problem.

- [ ] **Step 3: Commit** — `test(cloudflare): decisive proof — project role confined to its own environment; account manager unaffected`

---

## Task 13: Frontend permission constants

**Files:**
- Modify: `frontend/src/shared/constants/permissions.ts`

- [ ] **Step 1: Implement**

In `RESOURCES`: delete `LOKI_CONFIG: "loki_config",` and append:

```ts
  // Project-scoped twins. Distinct strings, never aliases — see the backend's
  // ProjectScopedPermissionCatalog.ASSIGNABLE, which contains only these.
  // Use these with <CanInProject> (project effective set). Use the
  // account-level names above with <Can>/hasPermission (global session set).
  PROJECT_CLOUDFLARE_CONFIG: "project_cloudflare_config",
  PROJECT_CLOUDFLARE_TUNNEL: "project_cloudflare_tunnel",
  PROJECT_CLOUDFLARE_HOSTNAME: "project_cloudflare_hostname",
  PROJECT_CLOUDFLARE_DNS: "project_cloudflare_dns",
  PROJECT_CLOUDFLARE_AUDIT: "project_cloudflare_audit",
  PROJECT_LOKI_CONFIG: "project_loki_config",
  PROJECT_ALERT_RULE: "project_alert_rule",
  PROJECT_INCIDENT: "project_incident",
```

In `PERMISSIONS`: delete the whole `LOKI_CONFIG` block; trim `ALERT_RULE` to `{ RESOURCE, READ }` and `INCIDENT` to `{ RESOURCE, READ }` (their retired actions no longer exist as permissions — this makes `tsc` a real safety net for Task 14); leave every `CLOUDFLARE_*` block intact (all still-live account-level atoms). Append `PROJECT_CLOUDFLARE_CONFIG` (`RESOURCE`, `READ`), `PROJECT_CLOUDFLARE_TUNNEL` (`RESOURCE`, `READ`, `CREATE`, `SYNC`, `REFRESH_STATUS` — no `DELETE`/`REVEAL_TOKEN`), `PROJECT_CLOUDFLARE_HOSTNAME` (`RESOURCE`, `READ`, `CREATE`, `UPDATE`, `DELETE`), `PROJECT_CLOUDFLARE_DNS` (`RESOURCE`, `READ`, `CREATE`, `UPDATE`, `DELETE`), `PROJECT_CLOUDFLARE_AUDIT` (`RESOURCE`, `READ`), `PROJECT_LOKI_CONFIG` (`RESOURCE`, `READ`, `MANAGE`), `PROJECT_ALERT_RULE` (`RESOURCE`, `CREATE`, `READ`, `UPDATE`, `DELETE`), `PROJECT_INCIDENT` (`RESOURCE`, `CREATE`, `READ`, `ACKNOWLEDGE`, `RESOLVE`) — each block's values are template-literal-derived from the matching `RESOURCES.PROJECT_*` constant, mirroring the exact existing pattern for every other resource in this file.

- [ ] **Step 2:** `cd frontend && npx tsc --noEmit` → expect exactly two errors, both `Property 'LOKI_CONFIG' does not exist`, in `log-viewer-manager.tsx` and `project-detail-view.tsx`. Task 14 fixes them.

- [ ] **Step 3: Commit** — `feat(permissions): add project_-prefixed resources, retire the split-away atoms`

---

## Task 14: Frontend consumer swaps (verified file-by-file — only 8 files actually change)

**Files needing changes:**

- [ ] **Step 1: `src/modules/projects/ui/project-detail-view.tsx`** — the 3 `CanInProject I={ACTIONS.READ}` launch-button gates: `RESOURCES.CLOUDFLARE_TUNNEL` → `RESOURCES.PROJECT_CLOUDFLARE_TUNNEL`; `RESOURCES.LOKI_CONFIG` → `RESOURCES.PROJECT_LOKI_CONFIG`; `RESOURCES.ALERT_RULE` → `RESOURCES.PROJECT_ALERT_RULE`.

- [ ] **Step 2: `src/modules/log-viewer/ui/log-viewer-manager.tsx`** — both `RESOURCES.LOKI_CONFIG` → `RESOURCES.PROJECT_LOKI_CONFIG` (action `MANAGE` already correct — `project_loki_config.manage` exists).

- [ ] **Step 3: `src/modules/alerting/ui/alerting-manager.tsx`** — all 4 `PERMISSIONS.ALERT_RULE.RESOURCE` → `PERMISSIONS.PROJECT_ALERT_RULE.RESOURCE` (actions `CREATE`/`UPDATE`/`DELETE` already correct).

- [ ] **Step 4: `src/modules/incidents/ui/incident-detail-panel.tsx`** — both `PERMISSIONS.INCIDENT.RESOURCE` → `PERMISSIONS.PROJECT_INCIDENT.RESOURCE`.

- [ ] **Step 5: `src/modules/incidents/ui/incidents-page-content.tsx`** — the create-incident button: `RESOURCES.INCIDENT` → `RESOURCES.PROJECT_INCIDENT`. `incident.create` no longer exists after Task 1, so leaving this unchanged would permanently hide the button; `tsc` cannot catch it since `Can`'s props are typed as plain `string`.

- [ ] **Step 6: `src/modules/cloudflare-dns/ui/dns-manager.tsx`** — resource swap AND the D9 dead-gate fix:
  - the **unbind zone** button (backed by `DELETE /environments/{id}/cloudflare-config`, gated server-side by `cloudflare_config.manage`): switch to `<CanInProject I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_CONFIG.RESOURCE}>` — the **account-level** name, deliberately (unbinding is trust-establishing, always excluded from `ASSIGNABLE`).
  - the edit/delete DNS record buttons (currently one dead `MANAGE` gate): split into `<CanInProject I={ACTIONS.UPDATE} a={PERMISSIONS.PROJECT_CLOUDFLARE_DNS.RESOURCE}>` around edit and `I={ACTIONS.DELETE}` around delete.

- [ ] **Step 7: `src/modules/cloudflare-tunnels/ui/tunnel-hostnames-panel.tsx`** — resource swap + D9 fix: both "Add hostname" buttons → `<CanInProject I={ACTIONS.CREATE} a={PERMISSIONS.PROJECT_CLOUDFLARE_HOSTNAME.RESOURCE}>`; the edit+remove button pair splits into `I={ACTIONS.UPDATE}`/`I={ACTIONS.DELETE}`, both on `PERMISSIONS.PROJECT_CLOUDFLARE_HOSTNAME.RESOURCE`.

- [ ] **Step 8: `src/modules/cloudflare-tunnels/ui/tunnels-manager.tsx`** — the single dead `CanInProject MANAGE CLOUDFLARE_TUNNEL` gate wraps three buttons with three different trust tiers now; split it (D8/D9 combined):
  - **refresh-status** → `<CanInProject I={ACTIONS.REFRESH_STATUS} a={PERMISSIONS.PROJECT_CLOUDFLARE_TUNNEL.RESOURCE}>`
  - **reveal-token** → `<CanInProject I={ACTIONS.REVEAL_TOKEN} a={PERMISSIONS.CLOUDFLARE_TUNNEL.RESOURCE}>` — deliberately the **account-level** name (D8): `CanInProject` reads global∪project-role, and `cloudflare_tunnel.reveal_token` can now only ever arrive via the global half.
  - **delete** → `<CanInProject I={ACTIONS.DELETE} a={PERMISSIONS.CLOUDFLARE_TUNNEL.RESOURCE}>`, same reasoning.
  Add a short comment recording why two of the three use the account-level name.

**Confirmed to need NO change** (verify by grep before assuming): `dashboard-sidebar.tsx`, `dashboard/page.tsx` (both gate on retained `INCIDENT.READ`, matching the global `GET /incidents`), the 4 admin `/admin/environments/[environmentId]/{alerting,dns,tunnels,logs}/page.tsx` routes (gate on retained account-level names or plain `ENVIRONMENT.READ`), `admin/incidents/page.tsx`, `account-dns-tab.tsx` (the Cloudflare-**account**-level DNS tab, correctly keeps `CLOUDFLARE_DNS`), `project-roles-section.tsx` (only uses `RESOURCES.PROJECT_ROLE`, unrelated).

- [ ] **Step 9:** `cd frontend && npx tsc --noEmit && npx eslint . && npm run test && npm run build` → all clean.

- [ ] **Step 10: Commit** — `feat(ui): point project-scoped gates at project_ resources; fix three permanently-dead MANAGE gates`

---

## Task 15: Locale files

**Files:**
- `frontend/locales/en/modules/roles.json`, `frontend/locales/vi/modules/roles.json`
- `frontend/locales/en/modules/cloudflare-tunnels.json`, `frontend/locales/vi/modules/cloudflare-tunnels.json`

Real key shapes (verified): group headings are `resources.<resource>`, per-atom copy is `catalog.<description_key>` = `catalog.permissions.<resource>.<action>`, both looked up via `t.has()` with a raw-string fallback in `project-role-form-dialog.tsx`/`role-form-dialog.tsx`.

- [ ] **Step 1: `roles.json` → `resources`** — retitle the retained account-level names for disambiguation (append "(account-level)"/"(cấp tài khoản)" or similar), delete `loki_config`, add all 8 new `project_*` group headings with "(this project)"/"(trong dự án)" suffixes, in both `en` and `vi`.

- [ ] **Step 2: `roles.json` → `catalog.permissions`** — delete `loki_config`, delete `alert_rule.{create,update,delete}`, delete `incident.{create,acknowledge,resolve}`; revise the retained copy to note "(requires Cloudflare account access)" where relevant; add all 8 new `project_*` groups with concrete, non-placeholder en+vi copy for every action (mirror the existing per-action copy style already used for `cloudflare_dns`/`cloudflare_tunnel`/etc., just reworded for the project-scoped framing — e.g. `project_cloudflare_dns.create`: "Create DNS records for this project" / "Tạo DNS record cho dự án này").

- [ ] **Step 3: `cloudflare-tunnels.json` → `errors`** — add `cloudflare_tunnel_hostname_environment_mismatch` and `cloudflare_insufficient_account_access` keys, both locales, real user-facing copy (not placeholder text).

- [ ] **Step 4: Verify key parity** — write a small throwaway python script (or reuse one from earlier in this session) that flattens both locale files' JSON and asserts the `en`/`vi` key sets are identical. Then cross-check that every `description_key` in `RbacPermissionCatalog.CATALOG` resolves to a real `catalog.<key>` entry in both locale files, and every distinct resource has a `resources.<resource>` entry.

- [ ] **Step 5: Commit** — `feat(i18n): distinct account-level vs project-scoped permission copy (en + vi)`

---

## Task 16: Full verification sweep and finish

**Files:** none (verification only).

- [ ] **Step 1: Backend gate**
```bash
cd backend && ruff check . && ruff format --check . \
  && python scripts/check_module_boundaries.py --strict \
  && uv run lint-imports \
  && uv run mypy app/modules/cloudflare/ app/modules/observability/ app/modules/projects/ app/modules/rbac/ \
  && uv run pytest -q
```
If `ruff` surfaces pre-existing debt in files this plan never touched, re-run scoped to `app/modules/{cloudflare,observability,projects,rbac}/ app/seeds/ alembic/versions/ tests/{cloudflare,observability,projects,rbac}/` and confirm THAT scope is clean. Do not fix unrelated files.

- [ ] **Step 2: Frontend gate**
```bash
cd frontend && npx tsc --noEmit && npx eslint . && npm run test && npm run build
```

- [ ] **Step 3: Migration round-trip against `itsm_test` only** — `alembic upgrade head` → `downgrade -1` → `upgrade head`, then `python -m app.seeds.seed_rbac` **in that order**, and confirm the seed logs zero `REFUSING to remove permission` lines (proof the migration fully drained the retired rows).

- [ ] **Step 4: Manual walkthrough against `itsm_test`** — reproduce Task 12's scenario in the UI: create the two projects on one shared account+zone, build a project role in the project-role editor (confirm the checkbox grid now shows only `… (this project)` groups and that "Delete tunnels"/"Reveal tunnel connector token" are absent), assign it, and confirm the collaborator sees a refresh-status button but no delete/reveal-token buttons and cannot touch the other project's hostname.

- [ ] **Step 5: `reviewing-code-against-skills` pass** over `git diff develop...HEAD` — `fastapi-modular-scaffold` for backend files, `nextjs-modular-architecture` for frontend. Fix loop capped at 2 rounds.

- [ ] **Step 6: `finishing-a-development-branch`** — branch this work as `fix/project-scoped-resource-split-and-tunnel-hostname-ownership` off `develop` (confirm actually on it, not committing to `develop`). Present the standard 3-option menu and wait for an explicit choice before any merge action, exactly like every other feature this session.

## Test / Verify Checklist

- [ ] Migration round-trip (`upgrade head` → `downgrade -1` → `upgrade head`) against `itsm_test` succeeds; permission counts match (81 total, 24 `project_%`, zero `loki_config`); a project role that held `cloudflare_tunnel.create` now holds `project_cloudflare_tunnel.create` and NOT `cloudflare_tunnel.create`.
- [ ] Task 12's decisive test fails before Tasks 1-11 and passes immediately after, with no further changes.
- [ ] `seed_rbac.py`'s new guard manually exercised once (temporarily remove a still-granted catalog line, run the seed, confirm `REFUSING...` is logged and nothing is deleted, restore the line).
- [ ] Full backend + frontend gates green per Task 16.
- [ ] Manual UI walkthrough of the decisive scenario passes against `itsm_test`.

## Risks

- This is the second-largest security-sensitive change this session, after the original Project Roles feature itself — a data migration touching every existing role's grants is the highest-risk single step; the round-trip verification and the `seed_rbac.py` guard are the two safety nets, not substitutes for careful review.
- `cloudflare_dns`/`cloudflare_audit` (account-level names) become unused-but-kept after this split (no route currently checks them) — kept for symmetry and in case a future account-level DNS/audit route is added; not a live gap today.
- Standing constraint: every step of implementation and manual verification targets `itsm_test` — never the live `itsm` database behind `business-chatbot-postgres`.
