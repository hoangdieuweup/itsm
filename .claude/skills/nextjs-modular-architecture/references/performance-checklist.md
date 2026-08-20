# Performance Checklist (fast load)

- **Server Components by default.** Add `"use client"` only on the leaf that actually needs interactivity/state/browser APIs — not on the whole page just because one child needs it.
- **Prefetch + hydrate, don't client-fetch-on-mount.** See `data-layer.md` — this is usually the single biggest win.
- **`next/dynamic` for heavy client-only widgets** (charts, rich text editors, large animated sections, anything with a big third-party dependency) so their JS isn't in the initial bundle:
  ```tsx
  const OrderChart = dynamic(() => import("@/modules/orders/ui/order-chart"), { ssr: false });
  ```
- **Streaming with `loading.tsx` + `<Suspense>`** so slow data doesn't block the whole route from rendering — show the shell immediately, stream in the slow part.
- **`next/image`** for every image (automatic sizing, lazy loading, modern formats) and **`next/font`** for fonts (no layout shift, no extra request waterfall).
- **No barrel files that re-export everything.** `export * from "./x"` in a module's `index.ts` kills tree-shaking and hides which parts are actually the public API — export only what's meant to be consumed elsewhere.
- **Route-level code splitting is automatic** in the App Router — don't manually split by route; do manually split heavy in-page widgets.
- **Watch bundle size** with `@next/bundle-analyzer` when adding a new large dependency, especially anything animation- or chart-related.
- **Error boundaries per route segment**, not just one global one — an `error.tsx` in `app/orders/` contains a crash to that section instead of taking down the whole app. A top-level `app/global-error.tsx` still needs `'use client'` and must render its own `<html>`/`<body>`, since the root layout unmounts on error.
