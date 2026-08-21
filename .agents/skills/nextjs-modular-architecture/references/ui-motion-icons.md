# UI, Motion, and Icons

## shadcn/ui — treat as source, not a dependency
Components generated via `npx shadcn@latest add <name>` land in `shared/ui/` as plain source files you own — they are not an npm package to keep in sync. Don't hand-patch the generated file piecemeal every time you need a variant; instead:
- Small style tweak → edit the generated component directly, once, deliberately.
- A composed, product-specific pattern (e.g. a settings-form card built from `Card` + `Input` + `Button`) → put it in `shared/ui/blocks/`, not back inside the primitive.
- A module-specific one-off composition → lives in that module's own `ui/`, not in `shared/`.

## Framer Motion — `LazyMotion` + `m`, not the full `motion` import
```tsx
// Avoid: pulls in the full animation engine on every page that imports this file
import { motion } from "framer-motion";
<motion.li layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} />
```
```tsx
// shared/lib/motion.tsx — load once, reuse everywhere
"use client";
import { LazyMotion, domAnimation, m } from "framer-motion";

export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <LazyMotion features={domAnimation}>{children}</LazyMotion>;
}
export { m };
```
```tsx
// modules/orders/ui/order-list-item.tsx
import { m } from "@/shared/lib/motion";
<m.li layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} />
```
Put shared variants/transitions (durations, easings) in `shared/lib/motion.ts` too, so animation feel stays consistent instead of every component inventing its own numbers. Respect `prefers-reduced-motion` — Framer Motion's `useReducedMotion()` hook, applied at the shared variant level, covers this once instead of per component.

## lucide-react — named imports only
```ts
// Correct — tree-shakeable
import { Truck, Clock, PackageCheck } from "lucide-react";

// Avoid — defeats tree-shaking, pulls in every icon
import * as Icons from "lucide-react";
```
If you need to pick an icon dynamically by name (e.g. a CMS-driven UI), build an explicit lookup table mapping known names to already-imported icon components — never a runtime string lookup into the barrel file.
