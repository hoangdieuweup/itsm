# Split Cloudflare and Projects Services/Repositories into Packages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the flat `services/` folders of the `cloudflare` (37 use cases) and `projects` (19) modules into sub-packages by aggregate, and turn their oversized `repository.py` files (1084 and 639 lines) into `repository/` packages, with no behaviour change.

**Architecture:** Pure moves. Each repository class pair (`Abstract*` + concrete, plus its row model) moves to one file per aggregate; `repository/__init__.py` re-exports every class, so `uow.py` and the repository tests keep importing `app.modules.<module>.repository` unchanged. Service files keep their names and move into `services/<group>/`; only their dotted import paths change in `dependencies.py`, `router.py`, `public.py` and tests.

**Tech Stack:** FastAPI, SQLAlchemy async, ruff (isort + F401), import-linter, pytest + testcontainers.

**Spec:** user request (2026-09-13): "chia services/{package} theo nhóm; repository → package", following the file-budget follow-up in `2026-09-13-clean-code-audit-fixes.md`.

## Global Constraints

- Branch `refactor/split-cloudflare-projects-packages`, stacked on `refactor/clean-code-audit-fixes`. Local commits only.
- fastapi-modular-scaffold rule #12 and `references/architecture.md#keeping-files-and-functions-small`: a file past ~500-600 lines becomes a subpackage (`repository/`), never a flatter file; `__init__.py` composes/re-exports the pieces (same as `utils/__init__.py`).
- Rule #9: one use case = one file — file and class names do not change.
- Rule #15: every `Abstract*` contract stays next to its concrete class.
- Intra-module tiers (`architecture.md#intra-module-import-order`): repository (tier 3) → services (tier 4) → dependencies (tier 5); moves must not add an import that points up a tier.
- `.importlinter` facade contracts forbid `app.modules.<m>.repository` / `.services` for other modules; `as_packages` defaults to true, so the new sub-modules stay covered.
- Behaviour must not change: no edits inside class bodies.

## Scope

**In:** `backend/app/modules/cloudflare/{repository.py, services/}`, `backend/app/modules/projects/{repository.py, services/}` and the files importing them.

**Out:** `cloudflare/router.py` (804 lines), `observability` (19 services, 515-line repository — candidate for the same treatment later), small modules (auth 5, rbac 6, notifications 7, users 1 service), renaming any file or class.

## Impact Assessment (GitNexus, upstream)

| Symbol | Risk | Mitigation |
|---|---|---|
| `CloudflareUnitOfWork` | **CRITICAL** (41 direct) | Not edited. Imports `app.modules.cloudflare.repository`, which keeps exporting every class via `repository/__init__.py`. |
| `ProjectsUnitOfWork` | **HIGH** (23 direct) | Same — `uow.py` untouched. |
| `CloudflareAccountRepository`, `DnsRecordRepository`, `CloudflareTunnelRepository`, `ProjectRepository`, `ProjectMemberRepository` | MEDIUM | Class bodies copied verbatim; only the defining file changes. |
| `SyncDnsRecords`, `SyncTunnels`, `CreateProject` (representative services) | LOW | File moves; importers updated by an asserted script. |

Importers to update: `cloudflare/dependencies.py` (37), `cloudflare/router.py` (37), `cloudflare/public.py` (2), `projects/dependencies.py` (19), `projects/router.py` (19), `tests/cloudflare/test_services.py` (31), `tests/projects/test_services.py` (16), `tests/cloudflare/test_dependencies.py` (1). No dotted-path `patch()`/`monkeypatch` targets, no migration imports.

## Target Layout

### `cloudflare/repository/`

| File | Classes |
|---|---|
| `accounts.py` | `AbstractCloudflareAccountRepository`, `CloudflareAccountRepository` |
| `account_managers.py` | `CloudflareAccountManagerRow`, `AbstractCloudflareAccountManagerRepository`, `CloudflareAccountManagerRepository` |
| `configs.py` | `AbstractCloudflareConfigRepository`, `CloudflareConfigRepository` |
| `dns_records.py` | `AbstractDnsRecordRepository`, `DnsRecordRepository` |
| `tunnels.py` | `AbstractCloudflareTunnelRepository`, `CloudflareTunnelRepository` |
| `tunnel_hostnames.py` | `AbstractTunnelHostnameRepository`, `TunnelHostnameRepository` |
| `__init__.py` | re-exports all of the above, `__all__` |

### `cloudflare/services/`

| Group | Use cases |
|---|---|
| `accounts/` | `create_account`, `update_account`, `delete_account`, `list_visible_accounts`, `reveal_token`, `test_connection`, `list_zones` |
| `managers/` | `assign_manager`, `update_manager`, `remove_manager`, `list_account_managers` |
| `configs/` | `create_config`, `update_config`, `delete_config` |
| `dns/` | `create_dns_record`, `update_dns_record`, `delete_dns_record`, `list_dns_records`, `sync_dns_records`, `create_account_dns_record`, `update_account_dns_record`, `delete_account_dns_record`, `list_account_dns_records` |
| `tunnels/` | `create_tunnel`, `delete_tunnel`, `list_tunnels`, `refresh_tunnel_status`, `reveal_tunnel_token`, `sync_tunnels`, `create_account_tunnel`, `delete_account_tunnel`, `list_account_tunnels` |
| `tunnel_hostnames/` | `add_tunnel_hostname`, `update_tunnel_hostname`, `remove_tunnel_hostname`, `list_tunnel_hostnames` |
| `traffic/` | `get_traffic_stats` |

### `projects/repository/`

| File | Classes |
|---|---|
| `projects.py` | `AbstractProjectRepository`, `ProjectRepository` |
| `environments.py` | `AbstractEnvironmentRepository`, `EnvironmentRepository` |
| `links.py` | `AbstractProjectLinkRepository`, `ProjectLinkRepository` |
| `members.py` | `ProjectMemberRow`, `AbstractProjectMemberRepository`, `ProjectMemberRepository` |
| `roles.py` | `ProjectRoleRow`, `AbstractProjectRoleRepository`, `ProjectRoleRepository` |
| `__init__.py` | re-exports all of the above, `__all__` |

### `projects/services/`

| Group | Use cases |
|---|---|
| `projects/` | `create_project`, `update_project`, `delete_project`, `list_visible_projects` |
| `environments/` | `create_environment`, `update_environment`, `delete_environment` |
| `links/` | `create_project_link`, `update_project_link`, `delete_project_link` |
| `members/` | `add_project_member`, `remove_project_member`, `list_project_members`, `assign_member_project_role` |
| `roles/` | `create_project_role`, `update_project_role`, `delete_project_role`, `list_project_roles`, `list_assignable_permissions` |

## Tasks

### Task 1: `cloudflare/repository.py` → package

- [ ] Split by top-level class with a script: each new file gets a one-line module docstring naming its table(s), the original import header, and its classes verbatim; a class referencing a class that now lives in a sibling file imports it from that sibling.
- [ ] `repository/__init__.py` imports every class from the sub-modules and lists them in `__all__`.
- [ ] `git rm` the old `repository.py`; `ruff check --fix --select F401,I` then `ruff format` on the new package only.
- [ ] Verify: `uv run ruff check app tests`, `uv run lint-imports`, `uv run python -c "from app.main import app"`, `CACHE__URL=redis://localhost:6379/0 uv run pytest tests/cloudflare -q` (15 pre-existing `test_router.py` failures expected, nothing else).
- [ ] Commit — `refactor(cloudflare): split repository.py into a package per aggregate`

### Task 2: `cloudflare/services/` → group packages

- [ ] `git mv` each file into its group (table above), add an empty `__init__.py` per group.
- [ ] Rewrite `app.modules.cloudflare.services.<name>` → `app.modules.cloudflare.services.<group>.<name>` across `backend/app` and `backend/tests` with a script that fails on any name missing from the mapping; re-sort imports with `ruff check --fix --select I` on the touched files.
- [ ] Verify as in Task 1, plus `scripts/check_module_boundaries.py --strict`; `grep -rn "cloudflare.services.[a-z_]*\b import" ` shows no flat path left.
- [ ] Commit — `refactor(cloudflare): group use cases into service packages`

### Task 3: `projects/repository.py` → package

- [ ] Same procedure as Task 1 with the projects mapping.
- [ ] Verify with `tests/projects` (all must pass).
- [ ] Commit — `refactor(projects): split repository.py into a package per aggregate`

### Task 4: `projects/services/` → group packages

- [ ] Same procedure as Task 2 with the projects mapping.
- [ ] Verify with `tests/projects`.
- [ ] Commit — `refactor(projects): group use cases into service packages`

### Task 5: Verification and review

- [ ] Full backend suite: 682 passed / 15 pre-existing failures, unchanged.
- [ ] `ruff check`, `lint-imports` (11/11), `check_module_boundaries.py --strict`, app import + OpenAPI path count unchanged.
- [ ] `node .gitnexus/run.cjs analyze --force`, `detect-changes --scope compare --base-ref refactor/clean-code-audit-fixes`, `check --cycles`.
- [ ] Every new file ≤ ~600 lines.

## Risks

- A class referencing a sibling class after the split → caught by F821/import smoke test; the split script adds sibling imports explicitly.
- Import re-sorting could reorder unrelated lines in touched files → limited to `--select I` on files the rewrite touched.
- Git may not detect the repository split as renames → history is still reachable via `git log --follow` on the new files' contents; acceptable.
