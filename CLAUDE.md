# ITSM Project — Claude Code Instructions

> This file provides instructions for the **Claude Code** agent.
> Read carefully before starting any task.

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | **Next.js** (App Router) | TypeScript, modular architecture |
| Backend | **FastAPI** | Python, modular scaffold |
| UI/UX | Follow **ui-ux-pro-max** skill | If available in `.claude/skills/` |
| Code Intelligence | **GitNexus** (MCP + CLI) | `npx gitnexus analyze` for indexing, MCP tools for impact/review |
| Database | TBD | Will be updated when DB is chosen |

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

---

### PHASE 0 — Understand the Task

1. Read the user's request carefully.
2. Gather repo context:
   - Current branch, working tree status
   - Recently modified files / related modules
   - Repo commit conventions
3. **Run `npx gitnexus analyze`** if the index is stale or this is the first task in the session. This ensures the code graph is up-to-date for impact analysis in later phases.
4. Determine scope:
   - Frontend only / Backend only / Full-stack
   - New feature / Bugfix / Refactor
5. If critical information is missing → **ask the user once**, do not guess.

**Output (Phase 0):** 3–5 line summary of task understanding + scope + confirmation that gitnexus index is current.

---

### PHASE 0.5 — Read Related Skills (MANDATORY before Plan & before editing code)

**Do not create a plan or edit code before reading related skills.**

1. Determine which skills to read based on scope:

| Scope | Required Skills |
|-------|----------------|
| Next.js / frontend | `.claude/skills/nextjs-modular-architecture/` |
| UI / component / page / layout / styling | `ui-ux-pro-max` (if available) |
| FastAPI / backend | `.claude/skills/fastapi-modular-scaffold/` |
| Full-stack (with UI) | All of the above |
| Every task | `.claude/skills/reviewing-code-against-skills/` |

2. **Read the full content** of each relevant skill (not just the name). Memorize key constraints:
   - Folder / module boundary
   - Import direction / layers (router → service → …)
   - Forbidden patterns / required patterns
   - UI: spacing, hierarchy, contrast, a11y, responsive, states (loading/empty/error)

3. List **3–7 bullet constraints** to apply in the plan (copied from skills, not made up).

**Output (Phase 0.5):**
```text
Skills read:
- nextjs-modular-architecture: <yes/no/skip>
- ui-ux-pro-max: <yes/no/skip>
- fastapi-modular-scaffold: <yes/no/skip>
- reviewing-code-against-skills: yes

Constraints to apply:
- ...
- ...
```

---

### PHASE 1 — Research & Verify (run when not 100% certain)

1. Look up official docs (Next.js, FastAPI, related libraries).
2. Check versions in use: `package.json` / `pyproject.toml`.
3. Record sources (URL + key excerpts).
4. Do not copy outdated patterns if docs have changed.
5. Cross-reference research results with **Phase 0.5 constraints** — prioritize repo skills over external blogs/tutorials.

**Output (Phase 1):** "Verified" + docs/link key. Or "Skip research — already certain".

---

### PHASE 2 — Plan (MANDATORY before editing code)

**Only write the plan after Phase 0.5 is complete.**

**GitNexus impact assessment is MANDATORY in this phase.** For every existing symbol you plan to modify:
1. Run `impact(target: "<symbol>", direction: "upstream")` to see what depends on it.
2. If risk is HIGH or CRITICAL → document mitigation in the plan.
3. Use `context()` to drill into high-risk dependents.
4. Include the impact summary in the "Impact Assessment" section of the plan.

The plan must follow this structure:

```markdown
# Plan: <task name>

## Goal
...

## Scope
- In:
- Out:

## Skills Applied
- nextjs-modular-architecture: ...
- ui-ux-pro-max: ... (mandatory if UI is involved)
- fastapi-modular-scaffold: ...
- (specific constraints to follow)

## Impact Assessment (GitNexus)
- Symbols to modify: ...
- Risk level per symbol: ...
- Affected processes/modules: ...
- Mitigation for HIGH/CRITICAL: ...

## Architecture Impact
- Next.js modules affected:
- UI surfaces / components affected:
- FastAPI modules affected:

## Steps
1. ...
2. ...

## Test / Verify Checklist
- [ ] ...

## Risks
- ...
```

Every step **must respect** Phase 0.5 constraints.
**Do not implement until the plan is complete.**

**Output (Phase 2):** Plan written. Notify user "Plan complete, proceed with implementation?" for large tasks.

---

### PHASE 3 — Implement (follow the plan)

1. Re-read Phase 0.5 constraints + plan before editing the first file.
2. Follow the **exact step order** from the plan.
3. Every change must respect:
   - **nextjs-modular-architecture** when touching frontend
   - **ui-ux-pro-max** when touching UI
   - **fastapi-modular-scaffold** when touching backend
4. Prefer small, commit-able changes.
5. Use clear variable/file names following repo conventions.
6. Run tests / typecheck / lint locally if the repo has scripts.
7. If uncertain mid-implementation → look up docs, do not guess. If conflict with skill → **prioritize skill**.

**Output (Phase 3):** Code changes + summary of files modified.

---

### PHASE 4 — Review Against Skills (MANDATORY)

Use the `reviewing-code-against-skills` skill on the diff just created.

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
[ ] ui-ux-pro-max (if UI involved): hierarchy, spacing, contrast, a11y, responsive, loading/empty/error states?
[ ] fastapi-modular-scaffold: correct layer (router/service/schema), no heavy logic in router?
[ ] No hardcoded secrets / sensitive URLs
[ ] Sufficient error handling & validation
[ ] Tests / typecheck pass (if available)
[ ] Diff contains no junk files (.env, node_modules, __pycache__…)
```

**Step 3: Fix Loop (MANDATORY if any check fails)**

If ANY item fails:
1. Fix the code.
2. Re-run `detect_changes(scope: "all")` + `check()`.
3. Re-evaluate the entire checklist.
4. **Repeat until ALL items pass.** Do not proceed to Phase 5 with any failing check.

**Output (Phase 4):** "Review PASS" + GitNexus detect_changes summary + short note (or list of fixes applied).

---

### PHASE 5 — Commit / PR

1. Check `git status` / diff, verify correct branch.
2. Commit messages follow **Conventional Commits**:
   - `feat: ...`
   - `fix: ...`
   - `refactor: ...`
3. Do not commit secrets or build artifacts.
4. If PR is needed: summary = Goal + Steps completed + Test checklist.

**Output (Phase 5):** Commit hash or PR link.

---

## Hard Rules (DO NOT BREAK)

1. **Read related skills before Plan and before editing code** (Phase 0.5). Do not plan/edit code without reading first.
2. **Do not skip Plan** when the task touches > 1 file or has architecture impact.
3. **Do not guess docs** — if uncertain, look up official documentation.
4. **Do not merge phases**: Read skills → Plan complete, then code; Review complete, then commit.
5. **Do not refactor beyond task scope** unless the user agrees.
6. Each phase must have a **clear output** before moving to the next.
7. "Quick fix" / "just one change" tasks → still require Phase 0 + 0.5 + 4 minimum; Phase 1–2 can be shortened if truly trivial.
8. **GitNexus is mandatory for impact-aware development.** Run `npx gitnexus analyze` at Phase 0 to keep the index current. Run `impact()` at Phase 2 for every symbol being modified. Run `detect_changes()` + `check()` at Phase 4 to verify changes. If Phase 4 detects unexpected impact or structural issues → loop-fix until clean. Skipping GitNexus checks is the same severity as skipping skill reads.

---

## Response Template After Each Phase

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

| Skills/Plugins | Description |
|-------|-------------|
| `nextjs-modular-architecture/` | Module boundary, folder structure, App Router patterns |
| `fastapi-modular-scaffold/` | Router → Service → Schema, dependency injection |
| `reviewing-code-against-skills/` | Review checklist against skill architecture |
| `full-stack-dev-workflow/` | Overall workflow (source of this file's content) |

---

## Activation Example

User: "Add an order creation endpoint + order form UI"

```
1. Phase 0 → summarize scope: full-stack (with UI)
2. Phase 0.5 → read nextjs-modular-architecture + ui-ux-pro-max + fastapi-modular-scaffold + reviewing-code-against-skills; list constraints
3. Phase 1 → look up FastAPI dependency / Next.js form patterns if needed
4. Phase 2 → write plan (with Skills Applied + API schema + page/UI module)
5. Phase 3 → implement following constraints read earlier
6. Phase 4 → review against skills (including UI checklist)
7. Phase 5 → commit when user confirms
```

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **itsm** (2010 symbols, 3875 relationships, 110 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
