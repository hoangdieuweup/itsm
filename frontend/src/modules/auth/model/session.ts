import { z } from "zod";
import { userSchema } from "@/entities/user";

/**
 * Mirrors the backend's MeResponse: user profile + resolved role/permissions.
 * The session discriminant (`status`) is frontend-only — the backend doesn't
 * track it; the fetch either succeeds (authenticated) or 401s (unauthenticated).
 */
export const meResponseSchema = z.object({
  user: userSchema,
  roleName: z.string(),
  permissions: z.array(z.string()),
});

export const authSessionSchema = z.discriminatedUnion("status", [
  z.object({
    status: z.literal("authenticated"),
    user: userSchema,
    roleName: z.string(),
    permissions: z.array(z.string()),
  }),
  z.object({
    status: z.literal("unauthenticated"),
    user: z.null(),
    roleName: z.literal(""),
    permissions: z.array(z.string()).length(0),
  }),
]);

export type AuthSession = z.infer<typeof authSessionSchema>;
