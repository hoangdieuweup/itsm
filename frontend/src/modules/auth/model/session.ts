import { z } from "zod";
import { userSchema } from "@/entities/user";

/**
 * Structural skeleton — no real session state yet. Shape will be finalized
 * by the SSO integration sub-issue (#5) alongside the backend session
 * contract; kept here so `ui/` and `hooks/` below have something to type
 * against without reaching into backend response shapes directly.
 */
export const authSessionSchema = z.object({
  status: z.enum(["authenticated", "unauthenticated", "loading"]),
  user: userSchema.nullable(),
});

export type AuthSession = z.infer<typeof authSessionSchema>;
