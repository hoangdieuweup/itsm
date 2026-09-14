import { z } from "zod";

/**
 * Mirrors the backend's LogoutResponse. `dxLogoutUrl` is the WeUp DX logout
 * URL the browser must visit to end its DX SSO session, or null when only this
 * app's session was ended.
 */
export const logoutResultSchema = z.object({
  dxLogoutUrl: z.url().nullable(),
});

export type LogoutResult = z.infer<typeof logoutResultSchema>;

export interface LogoutVariables {
  /** Also end the browser's WeUp DX SSO session, not just this app's session. */
  endDxSession: boolean;
}
