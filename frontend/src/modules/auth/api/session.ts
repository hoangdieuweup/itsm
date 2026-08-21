import { apiFetch, ApiRequestError } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { meResponseSchema, type AuthSession } from "../model/session";

/**
 * Fetches the current user's session from the backend's `/auth/me` endpoint.
 *
 * Session cookies (httpOnly, set by the OAuth callback) are sent automatically
 * via `credentials: "include"` in `apiFetch`. On success, the response is the
 * `MeResponse` envelope — Zod-validated here instead of type-asserted, per
 * nextjs-modular-architecture/references/data-layer.md.
 *
 * On auth failure (no cookie / expired / revoked), the backend returns a 401
 * which `apiFetch` converts to an `ApiRequestError` — caught here and mapped
 * to the "unauthenticated" session state so `AuthGuard` can redirect.
 */
export async function fetchAuthSession(): Promise<AuthSession> {
  try {
    const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.AUTH.ME);
    const me = meResponseSchema.parse(raw);
    return {
      status: "authenticated",
      user: me.user,
      roleName: me.roleName,
      permissions: me.permissions,
    };
  } catch (error) {
    if (error instanceof ApiRequestError) {
      return { status: "unauthenticated", user: null, roleName: "", permissions: [] };
    }
    throw error;
  }
}
