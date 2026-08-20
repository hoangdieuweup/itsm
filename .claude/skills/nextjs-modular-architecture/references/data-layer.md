# Data Layer — TanStack Query in Next.js App Router

## Reads: Server Component prefetch, not client-only useQuery
Making a whole page `"use client"` and fetching with `useQuery` from mount means the browser downloads JS, mounts, *then* fetches — a client-side waterfall that costs a full round trip before anything useful renders. Prefetch on the server instead:

```tsx
// app/orders/page.tsx (Server Component, stays this way)
import { HydrationBoundary, QueryClient, dehydrate } from "@tanstack/react-query";
import { fetchOrders, ordersKeys, OrderList } from "@/modules/orders";

export default async function OrdersPage() {
  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({
    queryKey: ordersKeys.list(),
    queryFn: fetchOrders,
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <OrderList /> {/* client component, calls useOrders() — cache is already warm */}
    </HydrationBoundary>
  );
}
```
`OrderList` still calls `useOrders()` on the client (so it gets refetching, cache, mutation-sync) but the first paint doesn't wait on a client fetch — the data is already in the cache when it hydrates. This is the single highest-leverage change for perceived load speed with TanStack Query in the App Router.

If a route is trivial and never needs client-side refetch or mutations, skip TanStack Query entirely and just `await` the fetch straight in the Server Component — don't add a query layer where plain RSC data fetching is enough.

## Suspense and error boundaries, not `isLoading`/`error` checks

Pair the prefetch above with `useSuspenseQuery` instead of `useQuery`, and let Next's `loading.tsx`/`error.tsx` file convention own the two states that used to be checked by hand in every component:

```ts
// modules/orders/api/use-orders.ts
export function useOrders() {
  return useSuspenseQuery({ queryKey: ordersKeys.list(), queryFn: fetchOrders, staleTime: 30_000 });
}
```
```tsx
// modules/orders/ui/order-list.tsx — no isLoading, no error, no optional chaining
export function OrderList() {
  const { data: orders } = useOrders();
  return <ul>{orders.map((o) => <OrderListItem key={o.id} order={o} />)}</ul>;
}
```

This only works safely because the query is prefetched server-side above — TanStack's own SSR guide is explicit that `useSuspenseQuery` is fine "as long as you always prefetch all your queries." `loading.tsx` at the route becomes the *one* place the loading UI is defined (not a skeleton reinvented per component), and `error.tsx` becomes the *one* error UI — but its "Try again" button needs `useQueryErrorResetBoundary()` to actually clear the failed query's cached error before Next's own `reset()` re-renders the segment, or the same error just re-throws immediately. See `references/layer-examples.md` for the full pattern, including where `<QueryErrorResetBoundary>` has to sit (`core/providers.tsx`, above every route's error boundary) and the real bug (tanstack/query#7606) this avoids.

## The response envelope and apiFetch
A backend following the matching convention (`fastapi-modular-scaffold`'s `references/api-contract.md`, or any backend using the same shape) returns one envelope for every endpoint, REST or SSE: `{ success, data, error }`, camelCase fields. Unwrap it in exactly one place so every fetcher gets back the plain payload, never the envelope:
```ts
// shared/lib/api-client.ts
export interface ApiErrorPayload {
  code: string;
  message: string;
  context?: Record<string, unknown>;
}

export class ApiRequestError extends Error {
  constructor(public code: string, message: string, public context?: Record<string, unknown>) {
    super(message);
  }
}

interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: ApiErrorPayload | null;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  const body = (await res.json()) as ApiEnvelope<T>;
  if (!body.success || body.error) {
    throw new ApiRequestError(body.error!.code, body.error!.message, body.error!.context);
  }
  return body.data as T;
}
```
`fetchOrders`/`shipOrder`/every other fetcher already shown in this file stays exactly as written — they call `apiFetch<Order[]>(...)` and receive the unwrapped payload. `ApiRequestError.code` is what a `useMutation`'s `onError` or an error boundary reads to decide what the user sees — see `references/i18n-and-errors.md`.

## Query key factory (one per module/entity)
```ts
// modules/orders/api/query-keys.ts
export const ordersKeys = {
  all: ["orders"] as const,
  lists: () => [...ordersKeys.all, "list"] as const,
  list: (filters?: Record<string, unknown>) => [...ordersKeys.lists(), filters] as const,
  detail: (id: string) => [...ordersKeys.all, "detail", id] as const,
};
```
Never inline `["orders", "list"]` string arrays in components — always go through the factory, so `invalidateQueries`/`removeQueries` targeting stays correct when the shape changes.

## Fetcher separate from hook, and validated, not just typed
```ts
// modules/orders/api/fetchers.ts
import { orderListSchema, type Order } from "@/modules/orders/model/schema";

export async function fetchOrders(): Promise<Order[]> {
  const data = await apiFetch<unknown>("/api/orders");
  return orderListSchema.parse(data);
}
```
`apiFetch<unknown>`, not `apiFetch<Order[]>` — the type parameter used to be an unchecked assertion about the shape; the Zod schema is what actually establishes it now, and the `Order` type is `z.infer<typeof orderSchema>`, derived from the same schema instead of hand-written and kept in sync by hope. `.parse()` throwing on a shape mismatch puts the query into the same `error` state a network failure would, instead of the mismatch surfacing later as `undefined` deep in a component. See `references/layer-examples.md` for the full schema (`model/schema.ts`) this depends on.
```ts
// modules/orders/api/use-orders.ts
"use client";
export function useOrders() {
  return useQuery({ queryKey: ordersKeys.list(), queryFn: fetchOrders, staleTime: 30_000 });
}
```
The fetcher has no React/Query dependency — it's callable from a Server Component (for prefetch) or a test, not just from the hook.

## Mutations: Server Action or Route Handler, always wrapped in `useMutation`
Do **not** use a Server Action to *read* data. Server Actions are POST-only and queued sequentially per client — using one for a GET-shaped read serializes requests that should run in parallel and bypasses HTTP caching/deduplication entirely. Reads go through a Server Component or a Route Handler (`GET`) + `useQuery`; Server Actions are for writes.

```ts
// modules/orders/api/actions.ts
"use server";
export async function shipOrderAction(orderId: string) {
  // ...perform the write...
  revalidateTag(`order-${orderId}`);
}
```
```ts
// modules/orders/hooks/use-mark-order-shipped.ts
"use client";
export function useMarkOrderAsShipped() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: shipOrderAction,
    onMutate: async (orderId) => {
      await queryClient.cancelQueries({ queryKey: ordersKeys.list() });
      const previous = queryClient.getQueryData<Order[]>(ordersKeys.list());
      queryClient.setQueryData<Order[]>(ordersKeys.list(), (old) =>
        old?.map((o) => (o.id === orderId ? { ...o, status: "shipped" } : o))
      );
      return { previous };
    },
    onError: (_err, _id, ctx) => ctx?.previous && queryClient.setQueryData(ordersKeys.list(), ctx.previous),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ordersKeys.list() }),
  });
}
```
A Route Handler (`POST /api/orders/:id/ship`) wrapped the same way is also fine — prefer it when the mutation must be callable from more than one client (mobile app, external integration) so it isn't tied to a Next.js Server Action.

## staleTime / gcTime
Set `staleTime` per query based on how often the data actually changes — don't leave everything on the default (0, i.e. "always stale"). Rarely-changing reference data (e.g. a list of countries) can use `staleTime: Infinity`; frequently-changing dashboards might use a short `staleTime` plus `refetchInterval`.
