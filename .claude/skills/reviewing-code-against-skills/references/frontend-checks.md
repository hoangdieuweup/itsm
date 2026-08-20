# Frontend Checks — Next.js / React

Run the tools first (`eslint`, `eslint-plugin-boundaries` if configured, `tsc --noEmit`), then check for these.

## Cross-module imports
A `modules/<a>/` file importing directly from `modules/<b>/ui|model|api` (instead of through `entities/` or `shared/`) is the single most common violation in `nextjs-modular-architecture` projects — it's what a baseline agent reaches for by default when two features need the same concept.

```ts
// violation
import { UserAvatar } from "@/modules/profile/ui/user-avatar";

// fix: promote the shared concept to entities/, import through its public API
import { UserAvatar } from "@/entities/user";
```
Also flag: a module's `index.ts` using `export *` instead of named exports (turns the public API into "everything," breaks tree-shaking, hides what's actually depended on).

## Missing SSR prefetch
A page component marked `"use client"` at the top level that calls `useQuery` with no corresponding server-side `prefetchQuery` + `HydrationBoundary` in its `page.tsx` — this causes a client-side fetch waterfall (blank shell, then JS boots, then fetch starts) instead of the data being warm on first paint. Flag any `app/**/page.tsx` that is itself `"use client"` and fetches data, or whose sole child client component fetches with no prefetch upstream.

## Framer Motion / lucide-react
- `import { motion } from "framer-motion"` instead of the shared `LazyMotion` + `m` wrapper — ships the full animation engine to every page that imports it.
- `import * as Icons from "lucide-react"` instead of named imports — defeats tree-shaking.

## Circular imports
`eslint`'s `import/no-cycle` reports these if configured — flag it as a gap if a changed `eslint.config.js` doesn't enable it. Don't confuse a real cycle (two files each importing the other, or a longer loop through a chain of files) with `next/dynamic`/`await import()` used for code-splitting — that's a normal, encouraged pattern, not a violation. A real cycle's fix is moving the shared piece into `entities/`/`shared/` so the dependency only points one way.

## Permission-gated UI
If the governing skill is `nextjs-modular-architecture` and the project has a `PermissionProvider`/`<Can>` pattern (see its `references/rbac-ui.md`), flag:
- A gated button/page whose corresponding backend route has no matching `require_permission` check — the client-side gate is decorative if the server doesn't also enforce it. Cross-check against the backend's routes when both halves changed together.
- `organizationId` passed into `PermissionProvider` (or read anywhere permission-sensitive) from a URL param, prop, or client state instead of the verified session — the same class of bug as an API route trusting a client-supplied org id.
- A role-assignment `<Select>`/dropdown listing every role in the system instead of only the roles the current user's own permissions allow granting.
- `children` removed/hidden via `<Can>` where the actual intent was disable-with-tooltip (a fixed toolbar losing a button mid-row) — check the surrounding layout, not just that a permission check exists.

## Suppression comments without a reason
`eslint`'s `eslint-comments/require-description` reports these if configured — flag it as a gap if a changed `eslint.config.js` doesn't enable it. Flag on sight regardless of tooling:
- `// eslint-disable-next-line` (or `/* eslint-disable */`) with no rule name — silences everything on the line/file, not just the one intended violation.
- Any `eslint-disable*`/`@ts-ignore`/`@ts-expect-error` with a rule name but no `-- reason` (or reason text) explaining why.
- `@ts-ignore` where `@ts-expect-error` would do — `@ts-ignore` stays silent forever even after the underlying error is fixed; `@ts-expect-error` re-flags itself, which is the entire point of writing one down.

## File and function size
`eslint`'s `complexity` rule flags a function over complexity 15 if the project's `eslint.config.js` enables it (`complexity: ["error", 15]`) — if it's missing from a changed config, flag that as a gap rather than silently skipping the check. File length: `max-lines` catches it if configured, otherwise run `wc -l` on each changed file and flag anything over ~500-600 lines. The fix in both cases is a folder (`ui/order-list/index.tsx` + siblings), never a flatter file — see the governing skill's `references/enforcement-and-conventions.md` for the split pattern it expects.

## API contract: envelope unwrapping and i18n
If the governing skill is `nextjs-modular-architecture`, its `references/data-layer.md` and `references/i18n-and-errors.md` are the source of truth. Flag:
- A fetcher returning the raw envelope (`{ success, data, error }`) instead of the unwrapped payload — callers shouldn't need to know the envelope exists. Unwrapping belongs in exactly one place (`apiFetch`), not repeated per fetcher.
- Any new user-facing string (error text, toast, label) added without first checking whether the project has i18n (`next-intl`/`i18next`/`react-i18next` in `package.json`, a `messages/`/`locales/` dir, a `middleware.ts` or `[locale]` segment). If i18n is present and the new code shows `error.message`/a hardcoded string directly instead of going through `t(...)`/`error.code`, that's a violation. If i18n is genuinely absent, a plain string is correct — don't flag it.
- An error handler that reads `error.message` for display when `error.code` is available and i18n is present — `code` should be looked up first, `message` used only as the fallback when the key is missing.

## Performance
- A route or component with a large third-party dependency (chart library, rich text editor) imported statically instead of via `next/dynamic(..., { ssr: false })`.
- `<img>` instead of `next/image`, or a custom `<link>`/`@font-face` instead of `next/font`.

If the governing skill isn't `nextjs-modular-architecture`, read its own rules before assuming these apply — a Vite SPA or a different architecture skill will have different specifics even if the shape of the mistake (tight coupling, waterfall fetching, unoptimized bundle) rhymes.
