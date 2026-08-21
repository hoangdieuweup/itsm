import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";

/**
 * Calls POST `/auth/logout` to revoke the DX token and clear session cookies.
 * The backend's `LogoutUser` service handles DX token revocation and cache
 * cleanup; the response clears the httpOnly session cookies via `Set-Cookie`.
 */
export async function logoutUser(): Promise<void> {
  await apiFetch<null>(API_CONFIG.ENDPOINTS.AUTH.LOGOUT, { method: "POST" });
}
