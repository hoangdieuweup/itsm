# Adapting to Vite (SPA, no SSR)

Use this instead of Next.js when there's no need for SSR/SEO — an internal admin tool, an authenticated-only dashboard. The layer structure (`app/ modules/ entities/ shared/`, the dependency rule, the entity-vs-shared decision order) stays identical. What changes:

- **Routing**: `app/` holds a router config (TanStack Router or React Router) instead of file-based routes; no `page.tsx`/`layout.tsx` conventions.
- **Reads**: no Server Components, so there's no server-side prefetch step — every read goes through `useQuery` calling a fetcher directly against the real API. Code-split at the route level via the router's lazy-loading (`React.lazy` / route-based `import()`), since there's no automatic RSC-based splitting.
- **Mutations**: no Server Actions — a mutation is a fetcher function (POST/PATCH/DELETE) wrapped in `useMutation`, same optimistic-update pattern as the Next.js version.
- **Env vars**: `import.meta.env` instead of `process.env`; `@t3-oss/env-core` (not `env-nextjs`) for the same Zod-validated pattern.
- Everything in `data-layer.md`, `ui-motion-icons.md`, `performance-checklist.md`, and `enforcement-and-conventions.md` still applies as-is (query key factories, LazyMotion, lucide-react imports, eslint-plugin-boundaries, naming).
