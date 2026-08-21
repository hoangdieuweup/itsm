import { z } from "zod";
import { userSchema } from "@/entities/user";
import { AUTH_STATUS, type AuthStatus } from "@/shared/constants/auth";

/**
 * Mirrors the backend's MeResponse: user profile + resolved role/permissions.
 * The session discriminant (`status`) is frontend-only — the backend doesn't
 * track it; the fetch either succeeds (authenticated) or 401s (unauthenticated).
 */
export const meResponseSchema = z.object({
  user: userSchema,
  roleName: z.string(),
  roleNames: z.array(z.string()).default([]),
  permissions: z.array(z.string()),
});

export const authSessionSchema = z.discriminatedUnion("status", [
  z.object({
    status: z.literal(AUTH_STATUS.AUTHENTICATED),
    user: userSchema,
    roleName: z.string(),
    roleNames: z.array(z.string()).default([]),
    permissions: z.array(z.string()),
  }),
  z.object({
    status: z.literal(AUTH_STATUS.UNAUTHENTICATED),
    user: z.null(),
    roleName: z.literal(""),
    roleNames: z.array(z.string()).default([]),
    permissions: z.array(z.string()).length(0),
  }),
]);

export type AuthSession = z.infer<typeof authSessionSchema>;
export type AuthenticatedAuthSession = Extract<
  AuthSession,
  { status: typeof AUTH_STATUS.AUTHENTICATED }
>;

/**
 * Type guard to check if a session is authenticated.
 */
export function isAuthenticated(
  session: AuthSession | null | undefined,
): session is AuthenticatedAuthSession {
  return session?.status === AUTH_STATUS.AUTHENTICATED;
}

export { AUTH_STATUS, type AuthStatus };

