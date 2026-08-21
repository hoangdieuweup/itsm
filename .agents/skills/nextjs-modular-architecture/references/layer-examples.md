# Layer-by-layer example, with runtime-validated data

One worked example, every file, continuing the `orders`/`user` scenario already used throughout this
skill (`references/layers-and-modules.md`, `references/data-layer.md`, `references/rbac-ui.md`) instead
of introducing a new one — so a reader who already has that scenario in mind sees exactly how the pieces
join up, not a disconnected snippet per file.

Grounded in real sources, not invented: Zod-in-the-`queryFn` is TanStack Query maintainer TkDodo's own
documented pattern (tkdodo.eu/blog/type-safe-react-query) — "instead of writing a type definition and
then asserting that something is that type, we write a schema and validate... at which point it
*becomes* that type." The `ui/model/api/lib` segment shape is Feature-Sliced Design's own vocabulary
(feature-sliced.design, fsd.how). The `cva` variant pattern is shadcn/ui's own documented approach
(Vercel Academy's shadcn/ui course, ui.shadcn.com).

## Why validate the network boundary, not just type it

`Promise<Order[]>` on a fetcher is a compile-time promise about a runtime value the compiler never
actually checked — a backend deploy that renames a field, or a network layer that returns an HTML error
page instead of JSON, produces `undefined` deep in a component with no error until something reads a
property that isn't there. A Zod schema validates the actual response and *infers* the TypeScript type
from that schema, so the two can never drift apart the way a hand-written `interface` and the real
payload can. `.parse()` throwing turns a silent shape mismatch into the exact same `error` state
TanStack Query already has a UI for — no new failure mode to handle, the existing one just fires
correctly instead of firing late, somewhere else, confusingly.

## `entities/user/` — the shared concept, schema included

```ts
// entities/user/model/schema.ts
import { z } from "zod";

export const userSchema = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string().email(),
  avatarUrl: z.string().url().nullable().optional(),
});

export type User = z.infer<typeof userSchema>;
```

The type is *derived* from the schema (`z.infer<typeof userSchema>`), not written separately and kept
in sync by hand — there is exactly one place that says what a `User` looks like.

```tsx
// entities/user/ui/user-avatar.tsx
import { Avatar, AvatarFallback, AvatarImage } from "@/shared/ui/avatar";
import type { User } from "@/entities/user/model/schema";

export function UserAvatar({ user, className }: { user: User; className?: string }) {
  const initials = user.name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <Avatar className={className}>
      <AvatarImage src={user.avatarUrl ?? undefined} alt={user.name} />
      <AvatarFallback>{initials}</AvatarFallback>
    </Avatar>
  );
}
```

```ts
// entities/user/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { userSchema, type User } from "@/entities/user/model/schema";

export async function fetchCurrentUser(): Promise<User> {
  const data = await apiFetch<unknown>("/api/me");
  return userSchema.parse(data);
}
```

```ts
// entities/user/api/use-current-user.ts
"use client";
import { useQuery } from "@tanstack/react-query";
import { fetchCurrentUser } from "@/entities/user/api/fetchers";

export function useCurrentUser() {
  return useQuery({ queryKey: ["user", "me"], queryFn: fetchCurrentUser, staleTime: 60_000 });
}
```

```ts
// entities/user/index.ts — curated public API, never `export *`
export { userSchema, type User } from "./model/schema";
export { UserAvatar } from "./ui/user-avatar";
export { useCurrentUser } from "./api/use-current-user";
```

## `modules/orders/model/` — schema, then the type it produces

```ts
// modules/orders/model/schema.ts
import { z } from "zod";
import { userSchema } from "@/entities/user";

export const orderStatusSchema = z.enum(["pending", "shipped", "delivered"]);
export type OrderStatus = z.infer<typeof orderStatusSchema>;

export const orderSchema = z.object({
  id: z.string(),
  orderNumber: z.string(),
  status: orderStatusSchema,
  createdBy: userSchema,
  totalAmount: z.number(),
});
export type Order = z.infer<typeof orderSchema>;

export const orderListSchema = z.array(orderSchema);
```

`orderSchema.createdBy` composes `entities/user`'s own `userSchema` rather than redeclaring the shape —
the same reuse `references/layers-and-modules.md` already established for the `User` *type*; a schema
is just as much a shared concept as the type it produces, and belongs to the same owner.

## `modules/orders/api/` — the fetcher validates, the hook stays thin

```ts
// modules/orders/api/query-keys.ts
export const ordersKeys = {
  all: ["orders"] as const,
  lists: () => [...ordersKeys.all, "list"] as const,
  list: (filters?: Record<string, unknown>) => [...ordersKeys.lists(), filters] as const,
  detail: (id: string) => [...ordersKeys.all, "detail", id] as const,
};
```

```ts
// modules/orders/api/fetchers.ts
import { apiFetch } from "@/shared/lib/api-client";
import { orderListSchema, type Order } from "@/modules/orders/model/schema";

export async function fetchOrders(): Promise<Order[]> {
  const data = await apiFetch<unknown>("/api/orders");
  return orderListSchema.parse(data);
}
```

`apiFetch<unknown>` — the type parameter that used to promise the shape (`apiFetch<Order[]>`) is now
`unknown`, honestly, because the schema is what actually establishes the shape a line later. Nothing
about `apiFetch` itself changes (`references/data-layer.md` still owns it) — only what fetchers do with
what it returns.

```ts
// modules/orders/api/use-orders.ts
"use client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { ordersKeys } from "@/modules/orders/api/query-keys";
import { fetchOrders } from "@/modules/orders/api/fetchers";

export function useOrders() {
  return useSuspenseQuery({ queryKey: ordersKeys.list(), queryFn: fetchOrders, staleTime: 30_000 });
}
```

`useSuspenseQuery`, not `useQuery` — its return type has no `isLoading`/`isError`, because `<Suspense>`
and the nearest error boundary own those two states now instead of every consuming component checking
them by hand (tanstack.com/query's own Suspense guide: "combining `useSuspenseQuery` with `<Suspense>`
and `<ErrorBoundary>` completely separates the loading, error, and success states"). This only works
because `app/orders/page.tsx` already prefetches this exact query — TanStack's SSR guide is explicit
that `useSuspenseQuery` is safe "as long as you always prefetch all your queries"; skip prefetching and
every first paint blocks on a client fetch instead of hydrating warm.

## `modules/orders/ui/` — a `cva` variant, motion, an entity composed in

```tsx
// modules/orders/ui/order-status-badge.tsx
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/shared/lib/utils";
import type { OrderStatus } from "@/modules/orders/model/schema";

const badgeVariants = cva("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", {
  variants: {
    status: {
      pending: "bg-amber-100 text-amber-800",
      shipped: "bg-blue-100 text-blue-800",
      delivered: "bg-green-100 text-green-800",
    },
  },
});

interface OrderStatusBadgeProps extends VariantProps<typeof badgeVariants> {
  status: OrderStatus;
  className?: string;
}

export function OrderStatusBadge({ status, className }: OrderStatusBadgeProps) {
  return <span className={cn(badgeVariants({ status }), className)}>{status}</span>;
}
```

One `cva` call enumerates every valid visual state as a first-class variant instead of an `if`/`switch`
picking a class string — adding a status is adding one line to `variants.status`, not hunting every
place a status renders. This is the same pattern shadcn/ui's own generated components (`button.tsx`,
`badge.tsx`) already use; a module-owned component composing a new variant set follows it too, per
`references/ui-motion-icons.md`'s "small style tweak vs. composed pattern" split.

```tsx
// modules/orders/ui/order-list-item.tsx
"use client";
import { m } from "@/shared/lib/motion";
import { Truck } from "lucide-react";
import { UserAvatar } from "@/entities/user";
import { OrderStatusBadge } from "@/modules/orders/ui/order-status-badge";
import type { Order } from "@/modules/orders/model/schema";

export function OrderListItem({ order }: { order: Order }) {
  return (
    <m.li
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center justify-between gap-4 rounded-lg border p-4"
    >
      <div className="flex items-center gap-3">
        <UserAvatar user={order.createdBy} className="size-8" />
        <div>
          <p className="font-medium">{order.orderNumber}</p>
          <p className="text-muted-foreground text-sm">${order.totalAmount.toFixed(2)}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {order.status === "shipped" && <Truck className="size-4 text-blue-600" aria-hidden />}
        <OrderStatusBadge status={order.status} />
      </div>
    </m.li>
  );
}
```

`UserAvatar` comes from `@/entities/user`, never `@/modules/profile/...` — the cross-module rule from
`references/layers-and-modules.md` holds inside a UI component exactly as much as inside a fetcher.
`m.li` and `Truck` follow `references/ui-motion-icons.md` exactly: `LazyMotion`'s `m`, never the full
`motion` import; a named `lucide-react` import, never a wildcard.

```tsx
// modules/orders/ui/order-list.tsx
"use client";
import { useOrders } from "@/modules/orders/api/use-orders";
import { OrderListItem } from "@/modules/orders/ui/order-list-item";

export function OrderList() {
  const { data: orders } = useOrders(); // no isLoading, no error — Suspense/ErrorBoundary own those

  return <ul className="flex flex-col gap-2">{orders.map((o) => <OrderListItem key={o.id} order={o} />)}</ul>;
}
```

No `if (isLoading)`, no `if (error) throw error`, no `orders?.` optional chaining — `useSuspenseQuery`
guarantees `data` is present whenever this component actually renders; if the fetch is pending, React
suspends and the *route's* `loading.tsx` shows instead, and if it fails, the *route's* `error.tsx` shows
instead. One loading UI, one error UI, per route — not a skeleton and an inline error message
reinvented in every component that happens to fetch something.

## `modules/orders/hooks/` — a mutation, optimistic, and a toast that goes through i18n too

```ts
// modules/orders/hooks/use-mark-order-shipped.ts
"use client";
import { toast } from "sonner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { ordersKeys } from "@/modules/orders/api/query-keys";
import { shipOrderAction } from "@/modules/orders/api/actions";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import type { Order } from "@/modules/orders/model/schema";

export function useMarkOrderAsShipped() {
  const queryClient = useQueryClient();
  const getErrorMessage = useApiErrorMessage();
  const t = useTranslations("orders");

  return useMutation({
    mutationFn: shipOrderAction,
    onMutate: async (orderId: string) => {
      await queryClient.cancelQueries({ queryKey: ordersKeys.list() });
      const previous = queryClient.getQueryData<Order[]>(ordersKeys.list());
      queryClient.setQueryData<Order[]>(ordersKeys.list(), (old) =>
        old?.map((o) => (o.id === orderId ? { ...o, status: "shipped" } : o))
      );
      return { previous };
    },
    onError: (error, _id, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(ordersKeys.list(), ctx.previous);
      toast.error(getErrorMessage(error));
    },
    onSuccess: () => toast.success(t("shipped_successfully")),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ordersKeys.list() }),
  });
}
```

The toast, not just the error boundary, is a place `error.message` leaks past i18n if you're not
watching for it: `onError`'s `toast.error(...)` goes through the exact same `useApiErrorMessage()` from
`references/i18n-and-errors.md` as `app/orders/error.tsx` below — one function, both call sites, so
adding a new backend error code updates every surface that shows it, not just the one you remembered to
check. `onSuccess`'s `toast.success(...)` is a plain static string, so it goes through the project's own
`useTranslations`/`t(...)` the same as any other user-facing copy — see `references/i18n-and-errors.md`'s
"check for i18n before writing any user-facing string." Without i18n in the project, both calls become
plain strings (`toast.error(error.message)`, `toast.success("Shipped successfully")`) — don't reach for
`useTranslations` speculatively; see that file's "Without i18n" section.

## `modules/orders/index.ts` — the module's public API

```ts
export { OrderList } from "./ui/order-list";
export { useMarkOrderAsShipped } from "./hooks/use-mark-order-shipped";
export { fetchOrders } from "./api/fetchers";
export { ordersKeys } from "./api/query-keys";
export type { Order, OrderStatus } from "./model/schema";
```

Curated, named exports — never `export *`. A sibling module (or `app/`) importing anything from
`orders` goes through this file; nothing else in `modules/orders/` is reachable from outside it.

## `app/orders/` — thin routing, prefetch, one loading source, one error boundary

```tsx
// app/orders/page.tsx
import { HydrationBoundary, QueryClient, dehydrate } from "@tanstack/react-query";
import { fetchOrders, ordersKeys, OrderList } from "@/modules/orders";

export default async function OrdersPage() {
  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({ queryKey: ordersKeys.list(), queryFn: fetchOrders });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <OrderList />
    </HydrationBoundary>
  );
}
```

No `<Suspense>` written here — `loading.tsx` existing at this route segment is what tells Next.js to
wrap the segment's content in one automatically. This is the one thing `loading.tsx` buys over writing
`<Suspense>` by hand: the boundary is guaranteed to exist at the route level without every page
remembering to add it, which is exactly what closes the gap in
tanstack/query#6116 ("`useSuspenseQuery` infinite refetch after SSR... the fix is to have at least one
boundary").

```tsx
// app/orders/loading.tsx — the one source every loading state for this route comes from
export default function OrdersLoading() {
  return (
    <ul className="flex flex-col gap-2" aria-busy>
      {Array.from({ length: 3 }, (_, i) => (
        <li key={i} className="h-[68px] animate-pulse rounded-lg bg-muted" />
      ))}
    </ul>
  );
}
```

```tsx
// app/orders/error.tsx
"use client";
import { useEffect } from "react";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import { Button } from "@/shared/ui/button";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";

export default function OrdersError({ error, reset }: { error: Error; reset: () => void }) {
  const getMessage = useApiErrorMessage();
  const { reset: resetQueries } = useQueryErrorResetBoundary();

  useEffect(() => {
    console.error(error);
  }, [error]);

  const tryAgain = () => {
    resetQueries(); // clear the failed query's cached error — without this it just re-throws the same error
    reset(); // tell Next.js to re-render this route segment
  };

  return (
    <div className="flex flex-col items-center gap-3 p-8 text-center">
      <p>{getMessage(error)}</p>
      <Button onClick={tryAgain}>Try again</Button>
    </div>
  );
}
```

`resetQueries()` before `reset()` is the non-obvious half, confirmed against a real reported bug
(tanstack/query#7606): Next's `reset()` alone only re-renders the segment — it does not clear
`useSuspenseQuery`'s cached error, so the same stale error re-throws immediately and the "Try again"
button appears to do nothing. `useQueryErrorResetBoundary()` reads from a `<QueryErrorResetBoundary>`
that has to sit *above* this error boundary in the tree — in `core/providers.tsx`, alongside
`QueryClientProvider`, not per-route:

```tsx
// core/providers.tsx
"use client";
import { useState } from "react";
import { QueryClient, QueryClientProvider, QueryErrorResetBoundary } from "@tanstack/react-query";
import { MotionProvider } from "@/shared/lib/motion";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <QueryErrorResetBoundary>{() => <MotionProvider>{children}</MotionProvider>}</QueryErrorResetBoundary>
    </QueryClientProvider>
  );
}
```

`useApiErrorMessage` is `references/i18n-and-errors.md`'s hook, unchanged — this is the file that
actually calls it, closing the loop from "here's the pattern" to "here's where it runs."

## Verified

Type-checked as a standalone project (`entities/user`, `modules/orders`, `app/orders`, `core/providers.tsx`,
and the `shared/lib`/`shared/ui` stubs referenced above) with `tsc --noEmit` in strict mode, against
`@tanstack/react-query`, `zod`, `class-variance-authority`, `framer-motion`, `lucide-react`, `sonner`,
and `next-intl` installed at their current versions — `0` errors, run twice across two drafts. This
caught two real mistakes before they landed here: an earlier `index.ts` exporting `ordersKeys` from
`./api/fetchers` (it only ever existed in `query-keys.ts`), and confirming `QueryErrorResetBoundary`/
`useQueryErrorResetBoundary` are real exports of the installed `@tanstack/react-query` version before
writing code that assumed they existed. Deleted after verification, same as every other code sample in
this skill; the point of running it was confirming the imports and types actually line up, not keeping
throwaway scaffolding around.

## Applying this to a new module

1. `model/schema.ts` first — the Zod schema, and the type as `z.infer` of it, before any fetcher exists to validate against it.
2. `api/query-keys.ts`, `api/fetchers.ts` (validates via `.parse()`), `api/use-*.ts` (thin `useQuery` wrapper).
3. `ui/` — compose from `shared/ui` primitives and `entities/` concepts; a new visual state is a `cva` variant, not a conditional class string.
4. `hooks/` — mutations, each wrapped in `useMutation` with optimistic update + invalidation.
5. `index.ts` — curated exports only.
6. The owning `app/**/page.tsx` — prefetch + `HydrationBoundary`; a sibling `error.tsx` using `useApiErrorMessage`.
