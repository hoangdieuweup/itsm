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
| Database | TBD | Will be updated when DB is chosen |

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
3. Determine scope:
   - Frontend only / Backend only / Full-stack
   - New feature / Bugfix / Refactor
4. If critical information is missing → **ask the user once**, do not guess.

**Output (Phase 0):** 3–5 line summary of task understanding + scope.

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

Mandatory checklist:

```text
[ ] nextjs-modular-architecture: module boundary, import direction, folder structure correct?
[ ] ui-ux-pro-max (if UI involved): hierarchy, spacing, contrast, a11y, responsive, loading/empty/error states?
[ ] fastapi-modular-scaffold: correct layer (router/service/schema), no heavy logic in router?
[ ] No hardcoded secrets / sensitive URLs
[ ] Sufficient error handling & validation
[ ] Tests / typecheck pass (if available)
[ ] Diff contains no junk files (.env, node_modules, __pycache__…)
```

If any item fails → **fix immediately**, then re-review.
Only proceed to Phase 5 when review **PASSES**.

**Output (Phase 4):** "Review PASS" + short note (or list of fixes applied).

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
