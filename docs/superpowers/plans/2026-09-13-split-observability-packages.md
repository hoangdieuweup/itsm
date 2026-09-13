# Split Observability Services/Repository into Packages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `observability` module the same layout `cloudflare` and `projects` got in `2026-09-13-split-cloudflare-projects-packages.md`: its 19 flat use cases grouped into service packages and its 515-line `repository.py` turned into a `repository/` package, with no behaviour change.

**Architecture:** Pure moves using the same scripts. Each `Abstract*`/concrete repository pair moves to one file per aggregate and `repository/__init__.py` re-exports every class, so `uow.py` and `tests/observability/test_repository.py` keep importing `app.modules.observability.repository`. Service files keep their names and move into `services/<group>/`; dotted imports change in `dependencies.py`, `router.py`, `app/scheduler.py` and `tests/observability/test_services.py`.

**Tech Stack:** FastAPI, SQLAlchemy async, ruff (isort + F401), import-linter, pytest + testcontainers.

**Spec:** user request (2026-09-13): "merge đi và tiếp tục xử lý observability" — apply the cloudflare/projects split to observability.

## Global Constraints

- Branch `refactor/split-observability-packages` from `develop` (7cdc6a9, after merging the previous three branches). Local commits only.
- fastapi-modular-scaffold rule #12 / `architecture.md#keeping-files-and-functions-small`: split into a subpackage; `__init__.py` re-exports the pieces.
- Rule #9: file and class names do not change. Rule #15: `Abstract*` contracts stay beside their concrete classes.
- Tier order (`architecture.md#intra-module-import-order`) unchanged: repository → services → dependencies.
- `.importlinter` names `app.modules.observability.repository` / `.services` as packages; `as_packages` defaults to true, so sub-modules stay covered.
- No edits inside class bodies; single-name imports left in parentheses after pruning are collapsed only when the AST is unchanged.

## Scope

**In:** `backend/app/modules/observability/{repository.py, services/}` and their importers.

**Out:** `observability/router.py`, `dependencies.py`, `utils/`; renaming files or classes; `cloudflare/router.py`.

## Impact Assessment (GitNexus, upstream)

| Symbol | Risk | Mitigation |
|---|---|---|
| `ObservabilityUnitOfWork` | **HIGH** (20 direct) | Not edited — `uow.py` keeps importing `app.modules.observability.repository`, re-exported by `repository/__init__.py`. |
| `LokiConfigRepository`, `AlertRuleRepository`, `IncidentRepository` | LOW | Class bodies copied verbatim. |
| `RunDriftReconciliation`, `HandleCloudflareWebhook`, `StreamLogTail` (representative services) | LOW | File moves; importers rewritten by the asserted script. |

Importers: `observability/dependencies.py` (18), `observability/router.py` (18), `app/scheduler.py` (1), `tests/observability/test_services.py` (20); `uow.py` and `tests/observability/test_repository.py` import the repository package path, which does not change. No non-Python references outside historical plan docs.

## Target Layout

### `observability/repository/`

| File | Classes |
|---|---|
| `loki_configs.py` | `AbstractLokiConfigRepository`, `LokiConfigRepository` |
| `alert_rules.py` | `AbstractAlertRuleRepository`, `AlertRuleRepository` |
| `incidents.py` | `AbstractIncidentRepository`, `IncidentRepository` |
| `__init__.py` | re-exports all of the above, `__all__` |

### `observability/services/`

| Group | Use cases |
|---|---|
| `loki/` | `create_loki_config`, `update_loki_config`, `delete_loki_config`, `get_loki_config`, `run_log_query`, `stream_log_tail` |
| `alert_rules/` | `create_alert_rule`, `update_alert_rule`, `delete_alert_rule`, `list_alert_rules`, `list_available_alerts` |
| `incidents/` | `create_manual_incident`, `get_incident`, `list_incidents`, `acknowledge_incident`, `resolve_incident` |
| `webhooks/` | `handle_cloudflare_webhook`, `handle_loki_webhook` |
| `reconciliation/` | `run_drift_reconciliation` |

## Tasks

### Task 1: `observability/repository.py` → package

- [ ] Run `split_repository.py` with the mapping above; `ruff check --fix --select F401,I`; collapse single-name parenthesised imports (AST-checked); `ruff format`.
- [ ] Gates: `ruff check app tests`, `lint-imports` 11/11, `check_module_boundaries.py --strict`, OpenAPI still 65 paths, `pytest tests/observability` with zero failures.
- [ ] `detect-changes --scope staged`, commit — `refactor(observability): split repository.py into a package per aggregate`

### Task 2: `observability/services/` → group packages

- [ ] Run `group_services.py` with the mapping above (`git mv`, empty `__init__.py` per group, dotted-import rewrite across `app/` and `tests/`); `ruff check --fix --select I` and `ruff format` on the rewritten files; no flat `services.<name> import` left.
- [ ] Same gates as Task 1; commit — `refactor(observability): group use cases into service packages`

### Task 3: Verification

- [ ] Every class body from the old `repository.py` appears verbatim in the package; every service move is a 100% rename.
- [ ] Full backend suite: 682 passed, only the 15 known `tests/cloudflare/test_router.py` failures.
- [ ] `gitnexus analyze --force`, `detect-changes --scope compare --base-ref develop`, `check --cycles`.

## Risks

- `app/scheduler.py` lives outside the module; the rewrite scans all of `backend/app`, and the app import gate plus the full suite cover it.
- Group name `loki` is a sub-package of `services`; absolute imports of `app.integrations.loki` are unaffected.
