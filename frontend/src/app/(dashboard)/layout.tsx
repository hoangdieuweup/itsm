import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { AuthGuard, UserMenu, authKeys, fetchAuthSession } from "@/modules/auth";

/**
 * Server Component: prefetches the auth session query and hands it down via
 * `HydrationBoundary` so `AuthGuard`/`UserMenu`'s `useSuspenseQuery` resolves
 * from a warm cache on first paint instead of a client-side waterfall — see
 * .claude/skills/nextjs-modular-architecture/references/data-layer.md.
 */
export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const queryClient = createQueryClient();
  await queryClient.prefetchQuery({
    queryKey: authKeys.session(),
    queryFn: fetchAuthSession,
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <AuthGuard>
        <div className="flex flex-1 flex-col">
          <header className="flex items-center justify-between border-b px-6 py-3">
            <span className="font-semibold">ITSM</span>
            <UserMenu />
          </header>
          <main className="flex flex-1 flex-col p-6">{children}</main>
        </div>
      </AuthGuard>
    </HydrationBoundary>
  );
}
