# Enforcing the Layers

Conventions decay without enforcement. Use `eslint-plugin-boundaries` to turn the dependency rule into a build failure instead of a code-review reminder.

```js
// eslint.config.js
import boundaries from "eslint-plugin-boundaries";

export default [
  {
    plugins: { boundaries },
    settings: {
      "boundaries/elements": [
        { type: "app", pattern: "src/app/*" },
        { type: "module", pattern: "src/modules/*", capture: ["name"] },
        { type: "entity", pattern: "src/entities/*", capture: ["name"] },
        { type: "shared", pattern: "src/shared/*" },
      ],
    },
    rules: {
      "boundaries/element-types": [
        "error",
        {
          default: "disallow",
          rules: [
            { from: "app", allow: ["module", "entity", "shared"] },
            { from: "module", allow: ["entity", "shared"] }, // NOT other modules
            { from: "entity", allow: ["shared"] },            // NOT modules
            { from: "shared", allow: [] },
          ],
        },
      ],
    },
  },
];
```
This makes `modules/orders` importing from `modules/profile` a lint error, not a convention someone forgot.

## No circular imports
```js
// eslint.config.js — needs eslint-plugin-import
export default [
  {
    rules: {
      "import/no-cycle": "error",
    },
  },
];
```
Two files importing each other breaks under ESM's live-binding evaluation order and shows up as a value being `undefined` at a distance, hard to trace back to the cycle. `eslint-plugin-boundaries`' layer rules already prevent most cycles structurally (a module can't import another module, so they can't import each other); this rule catches the ones boundaries don't reach — two files inside the same module, or two entities.

This is unrelated to `next/dynamic(() => import(...))` or a plain `await import(...)` — a dynamic import for code-splitting is encouraged (see `performance-checklist.md`) and isn't a circular dependency. The rule to fix is two files each needing something the other exports; move the shared piece into `model/` (same slice) or `entities/`/`shared/` (cross-slice) so the dependency only points one way.

## No suppression comment without a reason
```js
// eslint.config.js — needs @eslint-community/eslint-plugin-eslint-comments
import eslintComments from "@eslint-community/eslint-plugin-eslint-comments";

export default [
  {
    plugins: { "eslint-comments": eslintComments },
    rules: {
      "eslint-comments/require-description": ["error", { ignore: [] }],
    },
  },
];
```
ESLint itself understands a `-- reason` suffix on any directive comment; `require-description` makes leaving it off an error instead of a habit:
```ts
// Rejected — no reason, and eslint-disable-next-line with no rule name silences everything on the line
// eslint-disable-next-line
const x: any = fetchLegacyPayload();

// Correct — specific rule, stated reason
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- legacy endpoint has no generated types yet, ticket JIRA-1234
const x: any = fetchLegacyPayload();
```
For TypeScript specifically, prefer `@ts-expect-error` over `@ts-ignore` — `@ts-expect-error` itself errors once the suppressed problem is fixed, so a stale suppression gets caught automatically instead of silently doing nothing forever:
```js
// eslint.config.js
{
  rules: {
    "@typescript-eslint/ban-ts-comment": [
      "error",
      { "ts-expect-error": "allow-with-description", "ts-ignore": true, minimumDescriptionLength: 10 },
    ],
  },
}
```
A suppression comment is a decision that has to survive the person who wrote it leaving the team. If there's no real reason, the fix is the actual problem, not the comment.

## Keeping files and functions small
```js
// eslint.config.js
export default [
  {
    rules: {
      complexity: ["error", 15],
      "max-lines": ["warn", { max: 600, skipBlankLines: true, skipComments: true }],
    },
  },
];
```
A component or hook file over ~500-600 lines is a sign it holds more than one concept — split it into a folder instead of leaving it flat, the same way a module itself splits into `api/ model/ ui/ hooks/`:
```
# order-list.tsx grew past readable size
ui/order-list/
├── index.tsx          # OrderList — composes the pieces below
├── order-list-item.tsx
└── order-list-filters.tsx
```
A function over complexity 15 is almost always doing more than one job — extract branches into smaller named functions, or move a decision into a dedicated hook. Don't disable the ESLint rule to make the warning go away; split the code instead.

## Type-safe env vars
Validate `process.env` once at startup instead of trusting `string | undefined` everywhere it's read:
```ts
// shared/config/env.ts
import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  server: { DATABASE_URL: z.string().url() },
  client: { NEXT_PUBLIC_API_URL: z.string().url() },
  experimental__runtimeEnv: { NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL },
});
```

## File naming
| Item | Convention |
|---|---|
| Files/folders | kebab-case (`order-status-badge.tsx`) |
| Components | PascalCase export |
| Hooks | `use-*.ts` file, `useCamelCase` export |
| Absolute imports | `@/*` → `src/*`, never relative chains like `../../../` |
