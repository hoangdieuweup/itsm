import type { AuthSession } from "../model/session";

/**
 * Structural stub only. Real implementation (sub-issue #5) will call the
 * backend's `/auth/oauth/dx/*` endpoints via `@/shared/lib/api-client` and
 * be wrapped in a TanStack Query hook in `../hooks/use-auth-session.ts`.
 */
export async function fetchAuthSession(): Promise<AuthSession> {
  return { status: "unauthenticated", user: null };
}
