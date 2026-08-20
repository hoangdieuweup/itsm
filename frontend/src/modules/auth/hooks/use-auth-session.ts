"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchAuthSession } from "../api/session";
import { authKeys } from "../api/query-keys";
import type { AuthSession } from "../model/session";

/**
 * Placeholder hook — always resolves to the "unauthenticated" skeleton
 * session from `api/session.ts` until sub-issue #5 wires the real DX SSO
 * endpoints. Consumers (auth-guard, user-menu) are written against this
 * hook's shape now so that swap-in later touches only `api/` and this file.
 *
 * `useSuspenseQuery`, not `useQuery`: the (dashboard) layout prefetches this
 * same query key server-side and hydrates it, so this never causes a client
 * waterfall — see .claude/skills/nextjs-modular-architecture/references/data-layer.md.
 */
export function useAuthSession() {
  return useSuspenseQuery<AuthSession>({
    queryKey: authKeys.session(),
    queryFn: fetchAuthSession,
    staleTime: 30_000,
  });
}
