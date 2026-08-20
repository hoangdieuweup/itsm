---
name: reviewing-code-against-skills
description: Use when reviewing changed backend or frontend code for compliance with the project's own architecture skill — after implementing a feature, before handing work back, or when asked to review/audit/check code against the project's conventions rather than generic style. Covers Python/FastAPI backends (N+1 queries, database ownership rules, security) and Next.js/React frontends (module boundaries, data-fetching pattern), driven by whichever architecture skill (e.g. fastapi-modular-scaffold, nextjs-modular-architecture) actually governs the changed files.
---

# Reviewing Code Against Skills

## Overview
A generic code review checks against style. This checks against **this project's own declared architecture** — the rules baked into whichever skill scaffolded it. Find the governing skill(s) for the changed files, pull its non-negotiable rules and common mistakes as the checklist, run the domain's standard tools, then add the checks tools can't do: N+1 queries, database ownership, cross-module imports, missing SSR prefetch.

## When to Use
- After implementing a feature or fixing a bug, before calling it done
- Before a PR, or before handing work back to the user
- User asks to "review this", "audit this", "check this follows the conventions"

Not for a plain style/bug pass with no project-specific architecture — use `code-review` for that. Not for a pure security audit — use `security-review` for that. This skill's job is narrower and more specific: does the code match what *this project's own* architecture skill says.

## Workflow
1. **GitNexus Change Detection (MANDATORY first step).** Before any skills-based review:
   - Run `detect_changes(scope: "all")` to analyze all uncommitted changes — maps git diff hunks to indexed symbols and shows affected processes.
   - Run `check()` to verify no circular imports or structural anomalies were introduced.
   - Compare the detected impact against the Phase 2 impact assessment (if one exists). Flag any unexpected symbols/processes not in the plan.
   - If `detect_changes` reveals unexpected blast radius or `check` finds issues → this is a review failure. The code must be fixed and re-checked before proceeding with the skills-based review below.
2. **Scope.** `git diff --name-only` against the base branch, or the files just written this session if there's no diff to read. Group changed files by directory/extension — don't review the whole repo unless asked for a full audit.
3. **Find the governing skill** for each group:
   - `.py` under an `app/` tree where each module has its own `constants.py`/`config.py`/`public.py` → `fastapi-modular-scaffold` conventions.
   - `.ts`/`.tsx` under `modules/`/`entities/`/`shared/` with TanStack Query and shadcn/ui → `nextjs-modular-architecture` conventions.
   - Neither shape matches → read the description of every skill in `~/.claude/skills/*/SKILL.md` and any project-local `.claude/skills/*/SKILL.md`, and match by the file extensions and directory shape actually present.
   - No skill matches → say so explicitly and fall back to `code-review`/`security-review`. Do not invent architecture rules that don't exist.
4. **Pull the checklist from the skill itself** — read its "Non-negotiable rules" / "Common Mistakes" sections fresh each time. Don't paraphrase from memory; skills change.
5. **Run the domain's tooling** (Quick Reference below), then read `references/backend-checks.md` or `references/frontend-checks.md` for the checks those tools structurally cannot catch.
6. **Report** using the shape in `references/report-format.md`. Every finding names the specific rule — and the skill it came from — that it violates.

## Quick Reference
| Domain | Tools | Also read |
|---|---|---|
| **All changes (first)** | GitNexus `detect_changes(scope: "all")` + `check()` | Compare against Phase 2 impact assessment |
| Python / FastAPI | `ruff check`, `ruff format --check`, `lint-imports`, `bandit -r app` | `references/backend-checks.md` |
| Next.js / React | `eslint` (+ `eslint-plugin-boundaries` if configured), `tsc --noEmit` | `references/frontend-checks.md` |
| Report shape | — | `references/report-format.md` |

A system with both a FastAPI backend and a Next.js frontend gets both passes — scope each to the files that actually changed in that half of the tree. Common monorepo shapes: `apps/api` + `apps/web`, or `backend/` + `frontend/` at the root. Don't rely on the folder name `app/` to tell the two apart — both a FastAPI project and a Next.js App Router project use it; the file extension (`.py` vs `.ts`/`.tsx`) is what actually distinguishes them.

## Common Mistakes
- **Skipping GitNexus change detection** — running only the linter without `detect_changes()` + `check()` first misses blast-radius issues and circular imports that no linter catches.
- Running only the linter and skipping the skill's own rules — a clean `ruff check` says nothing about a cross-module import or a missing prefetch.
- Citing a rule that "sounds right" instead of the skill's actual text — always name the skill and quote or closely paraphrase the exact rule.
- Reviewing the whole codebase when three files changed — scope to the diff unless a full audit was requested.
- Auto-fixing architectural findings — mechanical fixes (`ruff --fix`, `eslint --fix`) are fine to apply; a cross-module import or a missing N+1 guard needs a human decision, so report it instead of silently restructuring code.
- **Not looping on GitNexus failures** — if `detect_changes` reveals unexpected impact or `check` finds circular imports, the code must be fixed and re-checked, not just noted.
