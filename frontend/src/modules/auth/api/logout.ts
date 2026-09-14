import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { logoutResultSchema, type LogoutResult, type LogoutVariables } from "../model/logout";

/**
 * Calls POST `/auth/logout`. The backend revokes the stored DX tokens,
 * blacklists this app's session and clears its httpOnly cookies via
 * `Set-Cookie`. With `endDxSession`, the response also carries the WeUp DX
 * logout URL: DX ends its SSO session from its own cookie, so only a browser
 * navigation to that URL can do it.
 */
export async function logoutUser({ endDxSession }: LogoutVariables): Promise<LogoutResult> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.AUTH.LOGOUT, {
    method: "POST",
    data: { endDxSession },
  });
  return logoutResultSchema.parse(raw);
}
