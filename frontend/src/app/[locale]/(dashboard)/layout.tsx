import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { AuthGuard, authKeys, fetchAuthSession } from "@/modules/auth";
import { DashboardShell } from "./dashboard-shell";

/**
 * Server Component: prefetches the auth session query and hands it down via
 * `HydrationBoundary` so `AuthGuard`/`UserMenu`'s `useSuspenseQuery` resolves
 * from a warm cache on first paint instead of a client-side waterfall — see
 * .claude/skills/nextjs-modular-architecture/references/data-layer.md.
 */
export default async function DashboardLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const queryClient = createQueryClient();
  await queryClient.prefetchQuery({
    queryKey: authKeys.session(),
    queryFn: fetchAuthSession,
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <AuthGuard>
        <DashboardShell>{children}</DashboardShell>
      </AuthGuard>
    </HydrationBoundary>
  );
}
