---
name: full-stack-dev-workflow
description: >
  Standard workflow for building features/bugfixes on the Next.js + FastAPI stack in this project.
  You MUST read related architecture skills (nextjs-modular-architecture, fastapi-modular-scaffold,
  reviewing-code-against-skills) BEFORE planning and BEFORE editing code, invoke the superpowers
  plugin while receiving the request and planning (Phase 0-2), and invoke the ui-ux-pro-max plugin
  during implementation (Phase 3) whenever UI code is written — it is mandatory, not optional.
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

## Skills vs. Plugins — do not confuse the two

- **Skills** (`.claude/skills/...` in this repo, version-controlled): repo-specific architecture rules you *read*.
- **Plugins** (global, installed under `~/.claude/plugins/`, outside this repo): capabilities you *invoke*, each with a fixed place in the workflow — never interchangeable, never optional where marked mandatory.

| Skill / Plugin | Type | When to Use |
|--------------|------|-------------|
| **firecrawl MCP** | tool | Look up official docs when **not fully certain** about an API, config, or best practice. Do not guess. |
| **gitnexus / git** | tool | Understand the repo, branch, commit history, PR, and conflicts before editing / committing. |
| **gitnexus MCP** (impact/detect_changes/check/context) | tool — **MANDATORY** | `npx gitnexus analyze` at Phase 0 to index. `impact()` at Phase 2 for blast-radius before changing symbols. `detect_changes()` + `check()` at Phase 4 to verify changes match plan. Loop-fix if unexpected impact found. |
| **nextjs-modular-architecture** (`.claude/skills/nextjs-modular-architecture`) | skill | Any change on the Next.js side (App Router, module boundary, folder structure, TanStack Query, shadcn/ui). |
| **fastapi-modular-scaffold** (`.claude/skills/fastapi-modular-scaffold`) | skill | Any change on the FastAPI side (router, service, schema, dependency, module ownership). |
| **reviewing-code-against-skills** (`.claude/skills/reviewing-code-against-skills`) | skill | After coding — review the diff against the architecture + UI skills above. |
| **superpowers** | **plugin** | Invoke during **Phase 0 → Phase 2** — receiving/understanding the request and building the plan. Elevated planning/analysis capability, used *before* any code is written. |
| **ui-ux-pro-max** | **plugin — MANDATORY for UI** | Invoke during **Phase 3 (Implement)**, every time UI code is written or edited (layout, component, page, color, typography, spacing). Query its style/palette/font-pairing/a11y database and apply the result while writing the markup/CSS — this is an implementation-time check, not a planning-time skim. Skipping it on any UI implementation step is a workflow violation, same severity as skipping `fastapi-modular-scaffold` on a backend task. |

---

## PHASE 0 — Understand the Task (mandatory)

1. Read the user's request carefully.
2. Use **git** (or gitnexus if available) to gather:
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

## PHASE 0.25 — Multi-Agent Coordination & Split Decision (mandatory when issue-driven / automation-driven; skip for direct interactive chat with one user)

**Applies whenever this task was picked up from a shared queue (e.g. a GitHub issue polled by an automation)** where other agent runs — past, concurrent, or future — may touch the same repo. You act as your own supervisor here: no external process decides this for you.

1. **Staleness check (recover abandoned locks).** List other issues currently marked as claimed/in-progress in the same tracker. For each:
   - If its claim comment is older than this automation's execution timeout + a safety margin (e.g. timeout + 10 min) with no follow-up completion/PR/hand-back comment → treat it as **abandoned**, not active. Post a short comment explaining the previous run likely timed out or crashed, remove the stale in-progress marker, and (if that issue is unrelated to yours) leave it available for the next poll to pick up — do not silently leave a dead lock in place forever.
   - **Also sweep closed issues.** If any issue is already `closed` (merged/completed by a human or a prior run) but still carries the `in-progress` label, that label is leftover state from a claim that never got a proper hand-back — remove it as routine housekeeping (no comment needed, the issue is already resolved). Do this on every run, not just when you're about to claim something, so stale labels never linger on completed work and never get misread as an active claim by a future poll or by a human skimming labels.
2. **Conflict check (avoid parallel agents colliding on the same files).** Determine which paths/modules *your* candidate task would touch (from the issue body/labels, or your own read of the codebase). Compare against paths declared or reasonably inferable for any **still-active** (non-stale) in-progress issue:
   - **Overlap found** (same files/modules, or one depends on output the other hasn't produced yet) → **do not claim this issue now.** Skip it this cycle silently (no spam comment needed for a routine skip) and let a future poll re-check. This is "wait," not "fail."
   - **No overlap** → safe to proceed to claim.
3. **Claim immediately, then re-verify (close the race window).** Reading "no in-progress label yet" and then spending minutes on scope analysis before actually claiming leaves a window where a second concurrent run can read the same "unclaimed" state and start its own independent work (including its own independent split) — this has happened in practice (two runs each split the same parent issue into a different set of sub-issues). To avoid it:
   - As soon as steps 1–2 say "safe to proceed," **immediately** post the claim comment and add the `in-progress` label — *before* doing any deeper scope analysis, splitting, or implementation.
   - **Immediately after claiming, re-fetch the issue's comments/labels.** If you find another claim comment on the same issue with an earlier timestamp than yours (or a lower comment ID), you lost the race: **back off** — remove your own `in-progress` label if you added one, do not proceed further (no split, no implementation), and stop. The earlier claim wins; this is the tiebreaker, applied deterministically so two runs never both proceed.
   - If you find another claim comment with a *later* timestamp than yours, you won the race — proceed normally (the other run is expected to back off when it re-verifies).
   - Only after this re-verification passes do you move on to the split-vs-implement decision (step 4) or Phase 0.5.
4. **Split decision (you decide, not a human, not a fixed rule).** Once you've read the issue/spec enough to understand real scope (this may require a lightweight pass — doesn't need full Phase 0.5 depth yet):
   - Estimate whether the work is a single coherent, independently-reviewable, mergeable unit that plausibly fits one execution budget (see Phase 2/3 budget-awareness).
   - **If it clearly fits** → proceed as a single task (no split needed just because it's "issue-driven" — don't over-split trivial work).
   - **If it doesn't fit, or spans genuinely independent surfaces** (e.g. backend scaffold vs. frontend scaffold vs. a specific integration) → act as supervisor: create separate sub-issues, each with an explicit **"Owns (paths)"** section listing the directories/files it is responsible for so future conflict checks (step 2) can rely on it. Keep the paths **disjoint** across sub-issues so parallel agents can't collide. Convert the original issue into a tracking/epic issue (remove the pickup label, link the sub-issues), comment explaining the split and why, and stop — do not implement anything yourself in this run. The next poll(s) will pick up the sub-issues normally.
   - When in doubt between splitting and not — prefer **not splitting** trivial/ambiguous cases and instead ask (Phase 0 rule: ask once, don't guess) rather than fragmenting a task that didn't need it.
   - **Every issue you create or claim (parent, sub-issue, or standalone) must carry traceability metadata**, since this is how multiple agents/humans track shared state without a separate dashboard:
     - **Labels:** the pickup/status label (`agent-task` / `in-progress` / `needs-info` / `done`) **plus** a `component:*` label (`component:backend`, `component:frontend`, `component:docs`, `component:infra`, …matching the "Owns (paths)" scope) **and** a `type:*` label (`type:feature`, `type:bugfix`, `type:refactor`). Create any missing label with a sensible color/description rather than skipping it.
     - **Milestone:** attach the issue to the milestone representing its release/epic (e.g. `v0.1.0 — <epic name>`). If none exists yet for this body of work, create one (with a short description) before assigning — don't leave issues un-milestoned when they're part of a tracked epic.
     - Sub-issues inherit the parent's milestone unless the split explicitly represents a different release.

**Output (Phase 0.25):** One line per check — "Staleness: none found / reclaimed #N", "Conflict: none / skipped #N due to overlap with #M", "Claim: won / lost race to comment #X (backed off)", "Split: not needed / split into #A, #B, #C (owns: …)". If you skipped, lost the claim race, or split, stop here for this run.

---

## PHASE 0.5 — Read Related Skills (mandatory, before Plan and before editing code)

**Do not create a plan or edit code before reading related skills.**

1. Determine which skills **apply to the task** based on Phase 0 scope:

   | Scope | Required Skills (repo, read) |
   |-------|------------------------|
   | Next.js / frontend | **nextjs-modular-architecture** |
   | FastAPI / backend | **fastapi-modular-scaffold** |
   | Full-stack | **nextjs-modular-architecture** + **fastapi-modular-scaffold** |
   | Every coding task | **reviewing-code-against-skills** (to know the review criteria for later) |
   | Meta/tooling task (not touching Next.js/FastAPI/UI code) | Skip the table above; only cross-reference existing folder/skill conventions in the repo |

   Note: **`ui-ux-pro-max` is a plugin invoked in Phase 3 (Implement)**, not a skill read here — do not treat this table as covering it. If the task involves UI, flag that fact now so Phase 2's plan explicitly calls out the mandatory `ui-ux-pro-max` invocation for Phase 3.

2. **Read the full content** of each relevant skill (not just the name). Memorize key constraints:
   - Folder / module boundary
   - Import direction / layers (router → service → …; `shared → entities → modules → app`)
   - Forbidden patterns / required patterns
3. **Invoke the `superpowers` plugin** as part of this planning pass (Phase 0 → Phase 2 is its scope) — use it to strengthen the request/constraint analysis before Phase 2's plan is written.
4. List **3–7 bullet constraints** to apply in the plan (copied from skills, not made up).
5. If the repo contains other skills (`.claude/skills/`, `AGENTS.md`, …) relevant to the task domain → read those too.

**Output (Phase 0.5):**
```text
Skills read:
- nextjs-modular-architecture: <yes/no/skip>
- fastapi-modular-scaffold: <yes/no/skip>
- reviewing-code-against-skills: yes
- (other skills if applicable)

Plugins:
- superpowers: invoked (planning pass)
- ui-ux-pro-max: <flagged for mandatory Phase 3 invocation / n/a — no UI in scope>

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

**GitNexus impact assessment is MANDATORY in this phase.** For every existing symbol you plan to modify:
1. Run `impact(target: "<symbol>", direction: "upstream")` to see what depends on it.
2. If risk is HIGH or CRITICAL → document mitigation in the plan.
3. Use `context()` to drill into high-risk dependents.
4. Include the impact summary in the "Impact Assessment" section of the plan.

5. Write a concise plan in `PLAN.md` (or `.agents_tmp/PLAN.md`) with this structure:

```markdown
# Plan: <task name>

## Goal
...

## Scope
- In:
- Out:

## Skills Applied
- nextjs-modular-architecture: ...
- fastapi-modular-scaffold: ...
- (specific constraints to follow)

## Plugins
- superpowers: invoked during this planning pass (Phase 0-2)
- ui-ux-pro-max: <mandatory during Phase 3 if UI is involved — name the surfaces / n/a>
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
3. ...

## Test / Verify Checklist
- [ ] ...
- [ ] ...

## Risks
- ...
```

6. Every step in the plan **must respect** the constraints read in Phase 0.5:
   - **nextjs-modular-architecture** (boundary, folder, no domain leaking)
   - **fastapi-modular-scaffold** (router → service → repo, clear schemas)
   - If UI is involved, the plan's **Plugins** section must explicitly state `ui-ux-pro-max` will be invoked during Phase 3 for each affected surface — do not leave this implicit.
7. **If running under a bounded execution budget** (e.g. an automation/cron runner with a fixed timeout, not an interactive chat session): scope the plan so the unit of work fits comfortably within the budget with room for Phase 4 review. This should normally already be true — Phase 0.25 is responsible for splitting oversized issue-driven work *before* this point. If you reach Phase 2 and only now realize the scope is too large (e.g. Phase 0.25 was skipped, or the scope grew during Plan), go back and apply Phase 0.25's split decision rather than plowing ahead into a run you can't finish.
8. **Do not implement** until the plan is complete.

**Output (Phase 2):** `PLAN.md` file written (with Skills Applied + Impact Assessment sections). Notify user "Plan complete, proceed with implementation?" for large tasks; small tasks may continue directly.

---

## PHASE 3 — Implement (follow the plan)

1. **Before editing the first file:** quickly re-read Phase 0.5 constraints + plan (no need to re-read the entire skill if constraints are clearly noted).
2. Follow the **exact step order in PLAN.md**.
3. Every change must respect:
   - **nextjs-modular-architecture** when touching frontend
   - **fastapi-modular-scaffold** when touching backend
4. **Any UI code written or edited in this phase (component, page, layout, style, color, typography) MUST invoke the `ui-ux-pro-max` plugin** — query its style/palette/font-pairing/a11y database and apply the result *while* writing the markup/CSS, not as an afterthought. This is mandatory, not conditional on "if it seems needed" — skipping it is a workflow violation.
   - If the user supplied reference images (layout/color concept), reconcile them with `ui-ux-pro-max`'s output (palette, contrast, a11y) rather than eyeballing colors/spacing freehand.
5. Prefer:
   - Small, commit-able changes
   - Clear variable/file names following repo conventions
6. Run tests / typecheck / lint locally if the repo has scripts.
7. If **uncertain** mid-implementation → go back to **firecrawl MCP**, do not guess. If conflict with a skill → **prioritize the skill**, add a note in the plan.
8. **If running under a bounded execution budget:** track elapsed time against the budget. If it becomes clear the current unit of work will not finish (implementation + Phase 4 review + commit) within budget, **stop implementing new files immediately** and leave the work in a recoverable state:
   - If a coherent, reviewable slice is already committed → commit and push what's done, note in the issue/PR exactly what's left, and stop (do not claim `done`).
   - If nothing coherent is committed yet → do **not** leave the issue/lock in a state that looks actively in-progress forever. Revert the claim: comment explaining the task was too large for one run and needs to be split into smaller issues/PRs, then hand it back (e.g. remove the in-progress marker) so it is not permanently stuck.
   - Never let the clock run out silently while holding a claim with no trace of what happened.

**Output (Phase 3):** Code changes + summary of files modified + confirmation `ui-ux-pro-max` was invoked for any UI surfaces touched (or "n/a — no UI in this change").

---

## PHASE 4 — Review Against Skills (mandatory, bounded fix loop)

**Step 1: GitNexus Change Detection (MANDATORY before checklist)**

1. Run `detect_changes(scope: "all")` to analyze all uncommitted changes.
2. Run `check()` to verify no circular imports were introduced.
3. Compare the detected impact against the Phase 2 impact assessment:
   - Are there unexpected affected processes/symbols not in the plan?
   - Did the blast radius grow beyond what was planned?
4. If unexpected impact is found → **STOP. Update the plan, fix the code, re-run detect_changes. Loop until the actual impact matches the planned impact.**

**Step 2: Skills Review**

1. Use **reviewing-code-against-skills** on the diff just created.
2. Mandatory checklist:

```text
[ ] GitNexus detect_changes: actual impact matches planned impact from Phase 2?
[ ] GitNexus check: no circular imports or structural issues?
[ ] nextjs-modular-architecture: module boundary, import direction, folder structure correct?
[ ] If UI involved: was ui-ux-pro-max actually invoked in Phase 3 (not skipped)? hierarchy, spacing, contrast, a11y, responsive, loading/empty/error states applied per its output?
[ ] fastapi-modular-scaffold: correct layer (router/service/schema), no heavy logic in router?
[ ] No hardcoded secrets / sensitive URLs
[ ] Sufficient error handling & validation
[ ] Tests / typecheck pass (if available)
[ ] Diff contains no junk files (.env, node_modules, __pycache__…)
```

A UI change where `ui-ux-pro-max` was **not** invoked during Phase 3 fails this checklist outright — treat it as an architectural finding (Phase 3 must be redone with the plugin invoked), not a note to remember for next time.

**Step 3: Finding Classification & Fix Loop**

3. Classify every finding from the report, per `reviewing-code-against-skills`' own distinction:
   - **Mechanical** — lint/format/type errors, auto-fixable by tooling (`ruff --fix`, `eslint --fix`, `prettier`). Fix immediately, re-run tooling. **No round limit** — this is cheap and deterministic.
   - **Architectural** — module boundary violation, cross-module import, wrong layer, missing SSR prefetch, N+1 query, missing auth check, etc. These need a real decision, not a mechanical fix.

4. **Architectural findings get at most 2 fix→review rounds:**
   - Round 1: fix per the plan/skill's rule, re-run **reviewing-code-against-skills**.
   - Round 2 (only if findings remain): fix again, re-review.
   - **Do not attempt a 3rd round.** If findings are still failing after 2 rounds, that is a signal the spec/constraint is ambiguous or contradictory — not a reason to keep guessing.
   - **After each fix round:** re-run `detect_changes(scope: "all")` + `check()` to verify the fix didn't introduce new unexpected impact.

5. **Escalate instead of guessing** — trigger this immediately (don't wait for round 2 to finish) whenever:
   - Unresolved architectural findings remain after round 2, OR
   - `detect_changes` keeps revealing unexpected blast radius after fixes, OR
   - At any point you are genuinely uncertain how to resolve a finding (conflicting skill rules, missing spec detail, ambiguous requirement).

   When escalating:
   - **Stop implementing further.** Do not force a fix you are not confident is correct, and do not mark the task done.
   - If this task originated from a GitHub issue (issue-driven / automation workflow): post a comment on that issue stating exactly what is ambiguous or still failing — quote the specific skill rule and the specific file/line — add label `needs-info`, remove `in-progress` if present, and **stop**. Do not open a PR that silently ships known-unresolved architectural violations.
   - If working directly with a user in chat (no issue tracker involved): ask the user one focused question and wait for their answer before continuing.
   - Never merge, never self-approve, never silently ship code that fails its own architecture skill's rules just to "finish".

6. Only proceed to Phase 5 when: all GitNexus checks pass (actual impact = planned, no circular imports), all mechanical findings are fixed, all architectural findings are resolved within the 2-round cap, and tests/typecheck pass.

**Output (Phase 4):** "Review PASS" + GitNexus detect_changes summary + short note (fixes applied, rounds used) — or "Escalated: see issue #<n>" / "Escalated: asked user" if the loop was exhausted or ambiguity was hit.

---

## PHASE 5 — Branch / Commit / PR / Traceability (when user requests or task is complete)

1. **Never commit or push directly to `main` or `develop`**, for any change — including trivial docs/skill-only edits. Both branches only receive changes through a merged PR. This applies to every agent run: interactive chat, automation, and any parallel agent under Phase 0.25.

2. **Branch naming + merge target (Gitflow):**
   - `feature/<short-slug>` — new feature (e.g. `feature/sso-login`) → branch from `develop`, PR **into `develop`**.
   - `fix/<short-slug>` — bugfix → branch from `develop`, PR **into `develop`**.
   - `refactor/<short-slug>` — refactor, no behavior change → branch from `develop`, PR **into `develop`**.
   - `chore/<short-slug>` — tooling, deps, meta/docs-only (e.g. this skill file) → branch from `develop`, PR **into `develop`**.
   - `hotfix/<short-slug>` — urgent production fix → branch from **`main`**, PR **into `main`**. After merging, also propagate the same fix into `develop` (merge or cherry-pick) so it isn't lost when `develop` is next released.
   - If the repo already has its own branch-naming convention (check recent branch/PR history first) — **follow that instead** of inventing a new one.

3. Before branching: `git checkout develop && git pull` (or fetch) to branch from the latest `develop` (or `main` for a `hotfix/*`), avoiding stale-base conflicts — especially important when Phase 0.25 conflict-checking is in play with multiple agents.

4. Commit messages follow repo conventions (prefer Conventional Commits if the repo uses them):
   - `feat: ...`
   - `fix: ...`
   - `refactor: ...`
   - `chore: ...` / `docs: ...` for non-functional changes

5. Do not commit secrets or build artifacts.

6. Push the branch (not `main`/`develop`) and open a PR: summary = Goal + Steps completed + Test checklist. The PR must also carry traceability metadata, same principle as issues (Phase 0.25):
   - **Reference the issue** it closes (`Closes #N`) so status flows back automatically on merge.
   - **Same labels as the issue** (`component:*`, `type:*`) plus the PR's own state label if the repo uses one (e.g. `needs-review`).
   - **Same milestone as the issue**, so `git tag`/release notes for that milestone can enumerate every merged PR.

7. **`develop` → `main` is a release — never merge it without a version bump.** This merge (or an explicit "cut a release" request) is what triggers versioning, not each individual PR into `develop`:
   - Bump the version in every versioned manifest the repo has (e.g. `backend/pyproject.toml`, `frontend/package.json`) following SemVer (`vMAJOR.MINOR.PATCH`) unless the repo's existing tags/`CHANGELOG.md` show a different scheme already in use — follow that instead of inventing a new one.
   - Tag the resulting `main` commit `vX.Y.Z` and write/update `CHANGELOG.md` summarizing what merged since the last release (the milestone's PRs are a good source list).
   - If no versioning convention exists yet and this is the first release-worthy `develop → main` merge, ask the user once what scheme to adopt rather than guessing.
   - A regular `feature/fix/refactor/chore` PR into `develop` does **not** get its own version bump/tag — only the `develop → main` release merge does.

8. **Merging into `develop` or `main`** only happens when the user explicitly asks for it — this includes the `develop → main` release merge itself, which additionally always requires the version bump/tag from step 7 as part of that approval, never as an afterthought. For fully automated issue-driven work, opening the PR (into `develop`) is normally the end of the run's responsibility — leave merging to the user/maintainer unless the automation's own instructions explicitly grant merge authority.

**Output (Phase 5):** Branch name + PR link (never a bare commit hash on `main`/`develop`), with issue reference, labels, and milestone confirmed set. If this PR is a `develop → main` release merge, also confirm the version bump and tag.

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
9. **When issue-driven / running alongside other agents, run Phase 0.25 first.** You are your own supervisor: reclaim stale locks instead of leaving them stuck forever, skip (wait) instead of colliding with another active claim on overlapping paths, and split oversized work into disjoint sub-issues instead of guessing you can finish it in one bounded run. Never let two agents edit the same files concurrently, and never let a claimed issue sit locked with no trace of what happened to it.
10. **Every issue and PR gets traceability metadata** — status label, `component:*` label, `type:*` label, and milestone (Phase 0.25 / Phase 5). Create missing labels/milestones rather than skipping them. Never invent a version/tagging scheme unprompted — follow the repo's existing convention, or ask once if none exists.
11. **Never push directly to `main` or `develop`.** Every change — code, docs, or skill files — goes through a branch (Gitflow-style prefix: `feature/`, `fix/`, `refactor/`, `chore/` → PR into `develop`; `hotfix/` → PR into `main`) and a PR. This has no exceptions for "small" or "meta" changes. Merging `develop` or `main` requires explicit user approval.
12. **`develop` → `main` always means a version bump + tag.** This is a release, not a routine merge — never merge `develop` into `main` without bumping the version in every versioned manifest and tagging the resulting commit. A regular PR into `develop` never gets its own version bump.
13. **GitNexus is mandatory for impact-aware development.** Run `npx gitnexus analyze` at Phase 0 to keep the index current. Run `impact()` at Phase 2 for every symbol being modified. Run `detect_changes()` + `check()` at Phase 4 to verify changes. If Phase 4 detects unexpected impact or structural issues → loop-fix until clean. Skipping GitNexus checks is the same severity as skipping skill reads.

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
2. **Phase 0.5 → read nextjs-modular-architecture + fastapi-modular-scaffold + reviewing-code-against-skills; invoke `superpowers` plugin for the planning pass; list constraints (flag that `ui-ux-pro-max` will be mandatory in Phase 3)**
3. Phase 1 → firecrawl FastAPI dependency / Next.js form patterns if needed
4. Phase 2 → write PLAN.md (with Skills Applied + Plugins section + API schema + page/UI module)
5. **Phase 3 → implement; invoke `ui-ux-pro-max` plugin while building the UI (form, page, colors) — mandatory, not skippable**
6. Phase 4 → reviewing-code-against-skills (checklist confirms `ui-ux-pro-max` was actually invoked)
7. Phase 5 → commit when user confirms

---

End of skill. Start every task with Phase 0 → Phase 0.25 (if issue/automation-driven) → Phase 0.5.
