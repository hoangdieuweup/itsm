"use client";

import { redirect } from "next/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { useAuthSession } from "../hooks/use-auth-session";

/**
 * Client-side gate for `(dashboard)` routes. Currently always redirects to
 * `/login` because `useAuthSession` is a placeholder that never resolves to
 * "authenticated" — sub-issue #5 replaces the underlying hook, not this
 * component's logic.
 *
 * No `isPending` branch: `(dashboard)/layout.tsx` prefetches the session
 * query server-side and hands it down via `HydrationBoundary`, so the
 * `useSuspenseQuery` in `useAuthSession` resolves before this ever renders.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { data: session } = useAuthSession();

  if (session.status !== "authenticated") {
    redirect(ROUTES.login);
  }

  return <>{children}</>;
}
