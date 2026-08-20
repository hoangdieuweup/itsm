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
