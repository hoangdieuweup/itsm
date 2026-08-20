---
name: full-stack-dev-workflow
description: >
  Standard workflow for building features/bugfixes on the Next.js + FastAPI stack in this project.
  You MUST read related architecture skills (nextjs-modular-architecture, fastapi-modular-scaffold,
  ui-ux-pro-max when UI is involved, reviewing-code-against-skills) BEFORE planning and BEFORE editing code.
  Use when starting a new coding task (feature/fix/refactor) on Next.js and/or FastAPI,
  or when the user explicitly requests "follow the workflow" / "/feature" / "/fix" / "/implement".
triggers:
  - /workflow
  - /feature
  - /fix
  - /implement
  - when starting a new coding task (feature/bugfix/refactor) on Next.js or FastAPI
---

# Full-Stack Dev Workflow (Next.js + FastAPI)

You are the coding agent for this project. **Always follow this workflow** when working on features/bugfixes/refactors
involving Next.js and/or FastAPI. Do not skip phases. Do not skip mandatory steps.

## Related Skills / Tools in This Project

| Skill / Tool | When to Use |
|--------------|-------------|
| **firecrawl MCP** | Look up official docs when **not fully certain** about an API, config, or best practice. Do not guess. |
| **gitnexus / git** | Understand the repo, branch, commit history, PR, and conflicts before editing / committing. |
| **nextjs-modular-architecture** (`.claude/skills/nextjs-modular-architecture`) | Any change on the Next.js side (App Router, module boundary, folder structure, TanStack Query, shadcn/ui). |
| **fastapi-modular-scaffold** (`.claude/skills/fastapi-modular-scaffold`) | Any change on the FastAPI side (router, service, schema, dependency, module ownership). |
| **ui-ux-pro-max** (plugin) | Any UI/UX change (layout, component, spacing, a11y, visual hierarchy, responsive). |
| **reviewing-code-against-skills** (`.claude/skills/reviewing-code-against-skills`) | After coding — review the diff against the architecture + UI skills above. |
| **superpowers** | Elevated capabilities when needed (sandbox, special tools). Only use when a phase requires it. |

---

## PHASE 0 — Understand the Task (mandatory)

1. Read the user's request carefully.
2. Use **git** (or gitnexus if available) to gather:
   - Current branch, working tree status
   - Recently modified files / related modules
   - Repo commit conventions
3. Determine scope:
   - Frontend only / Backend only / Full-stack
   - New feature / Bugfix / Refactor
4. If critical information is missing → **ask the user once**, do not guess.

**Output (Phase 0):** 3–5 line summary of task understanding + scope.

---

## PHASE 0.5 — Read Related Skills (mandatory, before Plan and before editing code)

**Do not create a plan or edit code before reading related skills.**

1. Determine which skills **apply to the task** based on Phase 0 scope:

   | Scope | Required Skills/Plugins |
   |-------|------------------------|
   | Next.js / frontend | **nextjs-modular-architecture** |
   | UI / component / page / layout / styling | **ui-ux-pro-max** |
   | FastAPI / backend | **fastapi-modular-scaffold** |
   | Full-stack (with UI) | **nextjs-modular-architecture** + **ui-ux-pro-max** + **fastapi-modular-scaffold** |
   | Every coding task | **reviewing-code-against-skills** (to know the review criteria for later) |
   | Meta/tooling task (not touching Next.js/FastAPI/UI code) | Skip the table above; only cross-reference existing folder/skill conventions in the repo |

2. **Read the full content** of each relevant skill (not just the name). Memorize key constraints:
   - Folder / module boundary
   - Import direction / layers (router → service → …; `shared → entities → modules → app`)
   - Forbidden patterns / required patterns
   - **ui-ux-pro-max**: spacing, hierarchy, contrast, a11y, responsive, states (loading/empty/error)
3. List **3–7 bullet constraints** to apply in the plan (copied from skills, not made up).
4. If the repo contains other skills (`.claude/skills/`, `AGENTS.md`, …) relevant to the task domain → read those too.

**Output (Phase 0.5):**
```text
Skills read:
- nextjs-modular-architecture: <yes/no/skip>
- ui-ux-pro-max: <yes/no/skip>
- fastapi-modular-scaffold: <yes/no/skip>
- reviewing-code-against-skills: yes
- (other skills if applicable)

Constraints to apply:
- ...
- ...
```

---

## PHASE 1 — Research & Verify (mandatory if not fully certain)

**Only run this phase when** you are not 100% certain about the API, pattern, or correct approach for the version in use.

1. Use **firecrawl MCP** to look up:
   - Official docs (Next.js, FastAPI, related libraries)
   - Versions in use in the repo (package.json / pyproject)
2. Record sources (URL + key excerpts).
3. Do not copy outdated patterns if docs have changed.
4. Cross-reference research results with **Phase 0.5 constraints** — prioritize repo skills over external blogs/tutorials.

**Output (Phase 1):** Bullet "Verified" + docs/link key. If already certain → write "Skip research — already certain".

---

## PHASE 2 — Plan (mandatory, before editing code)

**Only write the plan after Phase 0.5 is complete.**

1. Write a concise plan in `PLAN.md` (or `.agents_tmp/PLAN.md`) with this structure:

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
3. ...

## Test / Verify Checklist
- [ ] ...
- [ ] ...

## Risks
- ...
```

2. Every step in the plan **must respect** the constraints read in Phase 0.5:
   - **nextjs-modular-architecture** (boundary, folder, no domain leaking)
   - **ui-ux-pro-max** when UI is involved (hierarchy, spacing, a11y, responsive, states)
   - **fastapi-modular-scaffold** (router → service → repo, clear schemas)
3. **If running under a bounded execution budget** (e.g. an automation/cron runner with a fixed timeout, not an interactive chat session): scope the plan so at least the first coherent, independently-mergeable unit of work (e.g. backend scaffold only, or one module) fits comfortably within the budget with room for Phase 4 review. Do not plan a single pass that spans backend scaffold + frontend scaffold + a full OAuth integration if that realistically needs more time than is available — split it into multiple issues/PRs instead (state this split explicitly in the plan and in the issue comment) rather than silently running out of time mid-implementation.
4. **Do not implement** until the plan is complete.

**Output (Phase 2):** `PLAN.md` file written (with Skills Applied section). Notify user "Plan complete, proceed with implementation?" for large tasks; small tasks may continue directly.

---

## PHASE 3 — Implement (follow the plan)

1. **Before editing the first file:** quickly re-read Phase 0.5 constraints + plan (no need to re-read the entire skill if constraints are clearly noted).
2. Follow the **exact step order in PLAN.md**.
3. Every change must respect:
   - **nextjs-modular-architecture** when touching frontend
   - **ui-ux-pro-max** when touching UI (component, page, layout, style)
   - **fastapi-modular-scaffold** when touching backend
4. Prefer:
   - Small, commit-able changes
   - Clear variable/file names following repo conventions
5. Run tests / typecheck / lint locally if the repo has scripts.
6. If **uncertain** mid-implementation → go back to **firecrawl MCP**, do not guess. If conflict with a skill → **prioritize the skill**, add a note in the plan.
7. **If running under a bounded execution budget:** track elapsed time against the budget. If it becomes clear the current unit of work will not finish (implementation + Phase 4 review + commit) within budget, **stop implementing new files immediately** and leave the work in a recoverable state:
   - If a coherent, reviewable slice is already committed → commit and push what's done, note in the issue/PR exactly what's left, and stop (do not claim `done`).
   - If nothing coherent is committed yet → do **not** leave the issue/lock in a state that looks actively in-progress forever. Revert the claim: comment explaining the task was too large for one run and needs to be split into smaller issues/PRs, then hand it back (e.g. remove the in-progress marker) so it is not permanently stuck.
   - Never let the clock run out silently while holding a claim with no trace of what happened.

**Output (Phase 3):** Code changes + summary of files modified.

---

## PHASE 4 — Review Against Skills (mandatory, bounded fix loop)

1. Use **reviewing-code-against-skills** on the diff just created.
2. Mandatory checklist:

```text
[ ] nextjs-modular-architecture: module boundary, import direction, folder structure correct?
[ ] ui-ux-pro-max (if UI involved): hierarchy, spacing, contrast, a11y, responsive, loading/empty/error states?
[ ] fastapi-modular-scaffold: correct layer (router/service/schema), no heavy logic in router?
[ ] No hardcoded secrets / sensitive URLs
[ ] Sufficient error handling & validation
[ ] Tests / typecheck pass (if available)
[ ] Diff contains no junk files (.env, node_modules, __pycache__…)
```

3. Classify every finding from the report, per `reviewing-code-against-skills`' own distinction:
   - **Mechanical** — lint/format/type errors, auto-fixable by tooling (`ruff --fix`, `eslint --fix`, `prettier`). Fix immediately, re-run tooling. **No round limit** — this is cheap and deterministic.
   - **Architectural** — module boundary violation, cross-module import, wrong layer, missing SSR prefetch, N+1 query, missing auth check, etc. These need a real decision, not a mechanical fix.

4. **Architectural findings get at most 2 fix→review rounds:**
   - Round 1: fix per the plan/skill's rule, re-run **reviewing-code-against-skills**.
   - Round 2 (only if findings remain): fix again, re-review.
   - **Do not attempt a 3rd round.** If findings are still failing after 2 rounds, that is a signal the spec/constraint is ambiguous or contradictory — not a reason to keep guessing.

5. **Escalate instead of guessing** — trigger this immediately (don't wait for round 2 to finish) whenever:
   - Unresolved architectural findings remain after round 2, OR
   - At any point you are genuinely uncertain how to resolve a finding (conflicting skill rules, missing spec detail, ambiguous requirement).

   When escalating:
   - **Stop implementing further.** Do not force a fix you are not confident is correct, and do not mark the task done.
   - If this task originated from a GitHub issue (issue-driven / automation workflow): post a comment on that issue stating exactly what is ambiguous or still failing — quote the specific skill rule and the specific file/line — add label `needs-info`, remove `in-progress` if present, and **stop**. Do not open a PR that silently ships known-unresolved architectural violations.
   - If working directly with a user in chat (no issue tracker involved): ask the user one focused question and wait for their answer before continuing.
   - Never merge, never self-approve, never silently ship code that fails its own architecture skill's rules just to "finish".

6. Only proceed to Phase 5 when: all mechanical findings are fixed, all architectural findings are resolved within the 2-round cap, and tests/typecheck pass.

**Output (Phase 4):** "Review PASS" + short note (fixes applied, rounds used) — or "Escalated: see issue #<n>" / "Escalated: asked user" if the loop was exhausted or ambiguity was hit.

---

## PHASE 5 — Commit / PR (when user requests or task is complete)

1. Use **git / gitnexus** to check:
   - `git status` / diff
   - Correct branch
2. Commit messages follow repo conventions (prefer Conventional Commits if the repo uses them):
   - `feat: ...`
   - `fix: ...`
   - `refactor: ...`
3. Do not commit secrets or build artifacts.
4. If PR is needed: open a PR with summary = Goal + Steps completed + Test checklist.

**Output (Phase 5):** Commit hash or PR link.

---

## Hard Rules (do not break)

1. **Read related skills before Plan and before editing code** (Phase 0.5). Do not plan/edit code without reading first.
2. **Do not skip Plan** when the task touches > 1 file or has architecture impact.
3. **Do not guess docs** — if uncertain, use **firecrawl MCP**.
4. **Do not merge phases**: Read skills → Plan complete, then code; Review complete, then commit.
5. **Do not refactor beyond task scope** unless the user agrees.
6. Each phase must have a **clear output** before moving to the next.
7. When the user says "quick fix" / "just one change" → still run Phase 0 + **0.5** + 4 minimum; Phase 1–2 can be shortened if truly trivial (but you still must read related skills).
8. **Architectural review findings get at most 2 fix→review rounds** (Phase 4). Never loop indefinitely trying to satisfy a skill's rules — if still failing after 2 rounds, or if genuinely ambiguous at any point, **escalate instead of guessing**: ask the user, or if issue-driven, comment on the issue + label `needs-info` + stop. Never ship a PR that silently violates its own governing skill's rules.

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

## Activation Example

User: "Add an order creation endpoint + order form UI"

You:
1. Phase 0 → summarize scope: full-stack (with UI)
2. **Phase 0.5 → read nextjs-modular-architecture + ui-ux-pro-max + fastapi-modular-scaffold + reviewing-code-against-skills; list constraints**
3. Phase 1 → firecrawl FastAPI dependency / Next.js form patterns if needed
4. Phase 2 → write PLAN.md (with Skills Applied + API schema + page/UI module)
5. Phase 3 → implement following constraints read earlier (UI follows ui-ux-pro-max)
6. Phase 4 → reviewing-code-against-skills (including UI checklist)
7. Phase 5 → commit when user confirms

---

End of skill. Start every task with Phase 0 → Phase 0.5.
