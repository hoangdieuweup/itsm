# ITSM Project — Agent Instructions

> This file provides instructions for the **Gemini / Antigravity** agent.
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

### PHASE 0 — Understand the Task

1. Read the user's request carefully.
2. Gather repo context: current branch, working tree status, related files/modules.
3. Determine scope:
   - Frontend only / Backend only / Full-stack
   - New feature / Bugfix / Refactor
4. If critical information is missing → **ask the user once**, do not guess.

**Output:** 3–5 line summary of task understanding + scope.

---

### PHASE 0.5 — Read Related Skills (MANDATORY before Plan & before editing code)

**Do not create a plan or edit code before reading related skills.**

| Scope | Required Skills/Plugins |
|-------|----------------|
| Next.js / frontend | `.claude/skills/nextjs-modular-architecture/` |
| UI / component / page / layout / styling | `ui-ux-pro-max` (if available) |
| FastAPI / backend | `.claude/skills/fastapi-modular-scaffold/` |
| Full-stack (with UI) | All of the above |
| Every task | `.claude/skills/reviewing-code-against-skills/` |

After reading, list **3–7 constraints** that will be applied (copied from skills, not made up).

**Output:**
```text
Skills read:
- nextjs-modular-architecture: <yes/no/skip>
- ui-ux-pro-max: <yes/no/skip>
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

Write a plan with this structure:

```markdown
# Plan: <task name>

## Goal
## Scope (In / Out)
## Skills Applied (+ specific constraints)
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
4. If uncertain mid-implementation → look up docs, do not guess.
5. Run tests / typecheck / lint if the repo has scripts.

**Output:** Code changes + summary of files modified.

---

### PHASE 4 — Review Against Skills (MANDATORY)

Checklist:

```text
[ ] nextjs-modular-architecture: module boundary, import direction, folder structure correct?
[ ] ui-ux-pro-max: hierarchy, spacing, contrast, a11y, responsive, states?
[ ] fastapi-modular-scaffold: correct layer (router/service/schema)?
[ ] No hardcoded secrets / sensitive URLs
[ ] Sufficient error handling & validation
[ ] Tests / typecheck pass
[ ] Diff contains no junk files
```

If any item fails → **fix immediately**, then re-review.

**Output:** "Review PASS" + short note.

---

### PHASE 5 — Commit / PR

1. Check `git status`, verify correct branch.
2. Commit messages follow **Conventional Commits**:
   - `feat: ...` / `fix: ...` / `refactor: ...`
3. Do not commit secrets or build artifacts.

---

## Hard Rules

1. **Read skills before Plan and before editing code** (Phase 0.5).
2. **Do not skip Plan** when the task touches > 1 file or has architecture impact.
3. **Do not guess docs** — if uncertain, look up official documentation.
4. **Do not merge phases**: Read skills → Plan → Code → Review → Commit.
5. **Do not refactor beyond scope** unless the user agrees.
6. Each phase must have a **clear output** before moving to the next.
7. "Quick fix" / "just one change" tasks → still require Phase 0 + 0.5 + 4 minimum.

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
