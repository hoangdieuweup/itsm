# ITSM Project — Agent Instructions

> This file provides instructions for the **Gemini / Antigravity** agent.
> Read carefully before starting any task.

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | **Next.js** (App Router) | TypeScript, modular architecture |
| Backend | **FastAPI** | Python, modular scaffold |
| UI/UX | **`ui-ux-pro-max` plugin — MANDATORY** | Not a repo skill, not optional. See rule below. |
| Code Intelligence | **GitNexus** (MCP + CLI) | `npx gitnexus analyze` for indexing, MCP tools for impact/review |
| Database | TBD | Will be updated when DB is chosen |

---

## Plugins vs. Skills (do not confuse the two)

- **Skills** = repo-local instructions under `.claude/skills/` (`nextjs-modular-architecture`, `fastapi-modular-scaffold`, `full-stack-dev-workflow`, `reviewing-code-against-skills`). Version-controlled with this repo.
- **Plugins** = globally-installed Claude Code capabilities (`ui-ux-pro-max`, `superpowers`) that live outside this repo (`~/.claude/plugins/`) and must be **invoked**, not just read. Each plugin has a fixed place in the workflow — they are not interchangeable:

| Plugin | Invoke at | Purpose |
|--------|-----------|---------|
| **`superpowers`** | **Phase 0 → Phase 2** (receiving the request, understanding scope, planning) | Elevated planning/analysis capabilities used while turning the user's request into a concrete plan — invoke it while framing the task, *before* any UI code is written. |
| **`ui-ux-pro-max`** | **Phase 3** (Implement), for any UI code | The mandatory design-check/reference step whenever writing or editing UI markup/styles — query its style/palette/font-pairing/a11y database and apply the result while implementing. Not a planning tool; it's consulted while the UI code is actually being written. |

### `ui-ux-pro-max` plugin — mandatory whenever implementing UI code, no exceptions

The backend scaffold shipped with quality gaps because architecture skills were treated as optional reading. **The same is not acceptable for UI/design work.** Any implementation step touching layout, a page, a component, color, typography, spacing, or visual design **MUST invoke the `ui-ux-pro-max` plugin during Phase 3** — querying its style/palette/font-pairing/a11y database and applying the result — before/while writing markup or CSS. "I already know Tailwind" is not a substitute. Skipping this plugin on a UI implementation step is a workflow violation, same severity as skipping `fastapi-modular-scaffold` on a backend task.

- If the user supplies reference images/screenshots for layout or color concept, treat those as **hard constraints** to reconcile with `ui-ux-pro-max`'s recommendations (palette, contrast, a11y) — not as something to eyeball freehand.

---

## GitNexus — Code Intelligence (MANDATORY)

GitNexus provides graph-based code intelligence for impact analysis, change detection, and structural checks. It is used in **three phases** of the workflow:

### CLI: `npx gitnexus analyze`

Run **at Phase 0** (or whenever the codebase has significantly changed) to index/re-index the project graph. This builds the symbol graph that all MCP tools depend on.

```bash
# Index the project (run from repo root)
npx gitnexus analyze

# With PDG (program dependence graph) for deeper analysis
npx gitnexus analyze --pdg
```

### MCP Tools (used in Plan & Review phases)

| Tool | Phase | Purpose |
|------|-------|---------|
| `impact` | **Phase 2** (Plan) | Blast-radius analysis — before changing a symbol, check what depends on it (upstream). Returns risk level (LOW/MEDIUM/HIGH/CRITICAL) and affected processes. |
| `detect_changes` | **Phase 4** (Review) | Analyze uncommitted changes — maps git diff hunks to symbols, shows affected processes. Use `scope: "all"` for both staged+unstaged. |
| `check` | **Phase 4** (Review) | Structural checks — detects circular imports and other graph anomalies. |
| `context` | **Phase 2 & 4** | 360° view of a symbol — all callers, callees, imports, process participation. Use to drill into high-risk items from `impact` or `detect_changes`. |

### Mandatory Usage Rules

1. **Before planning changes to existing symbols** → run `impact(target, direction: "upstream")` on each symbol you intend to modify. Include the risk assessment and affected processes in the Plan (Phase 2).
2. **After implementing** → run `detect_changes(scope: "all")` to see what your changes actually affect. Cross-reference with the impact assessment from Phase 2. Run `check()` to verify no circular imports were introduced.
3. **If `detect_changes` reveals unexpected impact or `check` finds issues** → this is a review failure. Fix the code, re-run the tools, and loop until clean.

---

## Mandatory: Full-Stack Dev Workflow

**Every task** (feature, bugfix, refactor) must follow the workflow below.
Do not skip phases. Do not skip mandatory steps.

### PHASE 0 — Understand the Task

1. Read the user's request carefully.
2. Gather repo context: current branch, working tree status, related files/modules.
3. **Run `npx gitnexus analyze`** if the index is stale or this is the first task in the session. This ensures the code graph is up-to-date for impact analysis in later phases.
4. Determine scope:
   - Frontend only / Backend only / Full-stack
   - New feature / Bugfix / Refactor
5. If critical information is missing → **ask the user once**, do not guess.

**Output:** 3–5 line summary of task understanding + scope + confirmation that gitnexus index is current.

---

### PHASE 0.25 — Multi-Agent Coordination & Split Decision (MANDATORY when issue-driven/automation-driven)

Applies whenever the task came from a shared queue (e.g. an `agent-task` GitHub issue picked up by automation) where other agent runs — past, concurrent, or future — may touch the same repo. You are your own supervisor here.

1. **Staleness check:** reclaim abandoned `in-progress` locks (claim comment older than the run timeout + safety margin, no follow-up) instead of leaving them stuck forever. Also sweep every run: if a `closed` issue still carries `in-progress` (leftover from a claim that never got a proper hand-back, e.g. a human merged/closed it directly), remove the label as routine housekeeping — never let a stale label on completed work get misread as an active claim.
2. **Conflict check:** if your candidate issue's paths overlap an active `in-progress` issue, skip it this cycle silently — wait, don't collide.
3. **Claim immediately, then re-verify — this closes a real race condition.** As soon as steps 1–2 clear, immediately post the claim comment + add `in-progress`, *before* any scope analysis or splitting. Then immediately re-fetch the issue's comments: if another claim comment has an earlier timestamp than yours, you lost the race — back off (remove your `in-progress` label, do nothing further, stop). Two concurrent runs must never both proceed past this point; skipping this step has caused duplicate work in practice (two runs each independently split the same parent issue).
4. **Split decision (you decide):** if the scope doesn't fit one execution budget or spans independent surfaces (e.g. backend vs frontend vs a specific integration), split into sub-issues with disjoint `Owns (paths)` sections, convert the parent into a tracking issue, and stop — do not implement in this run. Otherwise proceed as a single task.
5. **Traceability:** every issue/sub-issue you create or claim gets a status label (`agent-task`/`in-progress`/`needs-info`/`done`) + `component:*` + `type:*` label + a milestone (create if missing).

---

### PHASE 0.5 — Read Related Skills (MANDATORY before Plan & before editing code)

**Do not create a plan or edit code before reading related skills.**

| Scope | Required Skills (repo) |
|-------|-------------------------|
| Next.js / frontend | `.claude/skills/nextjs-modular-architecture/` |
| FastAPI / backend | `.claude/skills/fastapi-modular-scaffold/` |
| Full-stack | All repo skills above |
| Every task | `.claude/skills/reviewing-code-against-skills/` |

Also invoke the **`superpowers` plugin** here (it belongs to Phase 0 → Phase 2, not to implementation) while you finish framing the request and its constraints — see "Plugins vs. Skills" above.

After reading, list **3–7 constraints** that will be applied (copied from skills, not made up).

**Output:**
```text
Skills read:
- nextjs-modular-architecture: <yes/no/skip>
- fastapi-modular-scaffold: <yes/no/skip>
- reviewing-code-against-skills: yes

Constraints to apply:
- ...
```

---

### PHASE 1 — Research & Verify (if not 100% certain)

1. Look up official docs (Next.js, FastAPI, related libraries) when not fully certain.
2. Check versions in use from `package.json` / `pyproject.toml`.
3. Record sources (URL + key excerpts).
4. Cross-reference with Phase 0.5 constraints — **prioritize repo skills** over external blogs/tutorials.

**Output:** Bullet "Verified" + docs/link key. Or "Skip — already certain".

---

### PHASE 2 — Plan (MANDATORY before editing code)

Write a plan with this structure. Continue using the **`superpowers` plugin** here — planning is still within its Phase 0→2 scope.

**GitNexus impact assessment is MANDATORY in this phase.** For every existing symbol you plan to modify:
1. Run `impact(target: "<symbol>", direction: "upstream")` to see what depends on it.
2. If risk is HIGH or CRITICAL → document mitigation in the plan.
3. Use `context()` to drill into high-risk dependents.
4. Include the impact summary in the "Impact Assessment" section of the plan.

```markdown
# Plan: <task name>

## Goal
## Scope (In / Out)
## Skills Applied (+ specific constraints)
## Plugins to invoke during implementation (e.g. `ui-ux-pro-max` if UI is involved)
## Impact Assessment (GitNexus)
  - Symbols to modify: ...
  - Risk level per symbol: ...
  - Affected processes/modules: ...
  - Mitigation for HIGH/CRITICAL: ...
## Architecture Impact (Next.js / FastAPI modules affected)
## Steps (numbered)
## Test / Verify Checklist
## Risks
```

**Do not implement until the plan is complete.**

---

### PHASE 3 — Implement

1. Re-read Phase 0.5 constraints + plan before editing the first file.
2. Follow the exact step order from the plan.
3. Respect skill architecture in every change.
4. **Any UI code in this step (layout, component, page, color, typography, spacing) MUST invoke the `ui-ux-pro-max` plugin** — query its style/palette/font-pairing/a11y database and apply the result while writing the markup/CSS. This is a mandatory implementation-time check, not optional, not a planning-phase step.
5. If uncertain mid-implementation → look up docs, do not guess.
6. Run tests / typecheck / lint if the repo has scripts.

**Output:** Code changes + summary of files modified + note on which plugins were invoked (e.g. `ui-ux-pro-max` used for X).

---

### PHASE 4 — Review Against Skills (MANDATORY)

**Step 1: GitNexus Change Detection (MANDATORY before checklist)**

1. Run `detect_changes(scope: "all")` to analyze all uncommitted changes.
2. Run `check()` to verify no circular imports were introduced.
3. Compare the detected impact against the Phase 2 impact assessment:
   - Are there unexpected affected processes/symbols not in the plan?
   - Did the blast radius grow beyond what was planned?
4. If unexpected impact is found → **STOP. Update the plan, fix the code, re-run detect_changes. Loop until the actual impact matches the planned impact.**

**Step 2: Skills Checklist**

```text
[ ] GitNexus detect_changes: actual impact matches planned impact from Phase 2?
[ ] GitNexus check: no circular imports or structural issues?
[ ] nextjs-modular-architecture: module boundary, import direction, folder structure correct?
[ ] If UI touched: was ui-ux-pro-max actually invoked in Phase 3? hierarchy, spacing, contrast, a11y, responsive, states applied?
[ ] fastapi-modular-scaffold: correct layer (router/service/schema)?
[ ] No hardcoded secrets / sensitive URLs
[ ] Sufficient error handling & validation
[ ] Tests / typecheck pass
[ ] Diff contains no junk files
```

**Step 3: Fix Loop (MANDATORY if any check fails)**

If ANY item fails:
1. Fix the code.
2. Re-run `detect_changes(scope: "all")` + `check()`.
3. Re-evaluate the entire checklist.
4. **Repeat until ALL items pass.** Do not proceed to Phase 5 with any failing check.

**Output:** "Review PASS" + GitNexus detect_changes summary + short note.

---

### PHASE 5 — Branch / Commit / PR

1. **Never commit or push directly to `main` or `develop`** — no exceptions, including trivial docs/meta-only changes. Both only change via a merged PR.
2. **Gitflow branch/merge targets:**
   - `feature/<slug>`, `fix/<slug>`, `refactor/<slug>`, `chore/<slug>` — branch from an up-to-date **`develop`**, PR **into `develop`**.
   - `hotfix/<slug>` (urgent prod fix only) — branch from **`main`**, PR into **`main`**, then also merge/cherry-pick the same fix back into `develop` so it isn't lost on the next release.
3. Commit messages follow **Conventional Commits**:
   - `feat: ...` / `fix: ...` / `refactor: ...` / `chore: ...` / `docs: ...`
4. Do not commit secrets or build artifacts.
5. Push the branch and open a PR referencing the issue (`Closes #N` if applicable), carrying the same `component:*`/`type:*` labels and milestone as the issue.
6. Merging into `develop` requires explicit user approval — opening the PR is normally where an automated/agent run's responsibility ends.
7. **`develop` → `main` = a release. Never do this without a version bump.** When a PR merges `develop` into `main` (or a maintainer asks to cut a release):
   - Bump the version (SemVer `vMAJOR.MINOR.PATCH`) in every versioned manifest that has one (e.g. `backend/pyproject.toml`, `frontend/package.json`).
   - Tag the resulting `main` commit `vX.Y.Z` and write/update `CHANGELOG.md` for that version.
   - Still requires explicit user approval to merge/tag/publish — do not self-trigger a release.

---

## Hard Rules

1. **Read skills before Plan and before editing code** (Phase 0.5).
2. **Do not skip Plan** when the task touches > 1 file or has architecture impact.
3. **Do not guess docs** — if uncertain, look up official documentation.
4. **Do not merge phases**: Read skills → Plan → Code → Review → Commit.
5. **Do not refactor beyond scope** unless the user agrees.
6. Each phase must have a **clear output** before moving to the next.
7. "Quick fix" / "just one change" tasks → still require Phase 0 + 0.5 + 4 minimum.
8. **Never push directly to `main` or `develop`.** Every change goes through a branch + PR, with no exception for small/meta changes. `feature/fix/refactor/chore` branches target `develop`; only `hotfix/*` targets `main` directly. Merging requires explicit user approval.
9. **`develop` → `main` is a release, not a routine merge.** Always bump the version (SemVer) and tag `main` when this merge happens — never merge `develop` into `main` without a version bump.
10. **Run Phase 0.25 first for issue/automation-driven work.** Claim immediately and re-verify (tiebreak on claim-comment timestamp) before any scope analysis — never let two concurrent runs both proceed past the claim step on the same issue.
11. **GitNexus is mandatory for impact-aware development.** Run `npx gitnexus analyze` at Phase 0 to keep the index current. Run `impact()` at Phase 2 for every symbol being modified. Run `detect_changes()` + `check()` at Phase 4 to verify changes. If Phase 4 detects unexpected impact or structural issues → loop-fix until clean. Skipping GitNexus checks is the same severity as skipping skill reads.

---

## Response Template

```text
## Phase X — <name>
**Status:** done | blocked | need-input
**What was done:** ...
**Output:** ...
**Next:** Phase Y or ask user
```

---

## Skills Reference

All skills are located in `.claude/skills/`:

- `nextjs-modular-architecture/` — Module boundary, folder structure, App Router patterns
- `fastapi-modular-scaffold/` — Router → Service → Schema, dependency injection
- `reviewing-code-against-skills/` — Review checklist against skill architecture
- `full-stack-dev-workflow/` — Overall workflow (this file is a summary)

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **itsm** (1161 symbols, 1944 relationships, 31 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/itsm/context` | Codebase overview, check index freshness |
| `gitnexus://repo/itsm/clusters` | All functional areas |
| `gitnexus://repo/itsm/processes` | All execution flows |
| `gitnexus://repo/itsm/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
