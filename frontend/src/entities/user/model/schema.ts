import { z } from "zod";

export const USER_STATUS = {
  ACTIVE: "active",
  BLOCKED: "blocked",
} as const;

export type UserStatus = (typeof USER_STATUS)[keyof typeof USER_STATUS];

export const userStatusSchema = z.enum([
  USER_STATUS.ACTIVE,
  USER_STATUS.BLOCKED,
]);

/**
 * Frontend representation of a user, matching the backend's `UserRead` schema.
 *
 * Post-RBAC cleanup: `role` and `departmentId` are removed from the `users`
 * table. Role is now resolved via `rbac.user_roles` and exposed through a
 * separate `RoleSummary` on the session, not on the user object itself.
 *
 * Fields use camelCase (backend `FrozenModel` is configured with
 * `alias_generator = to_camel`).
 */
export const userSchema = z.object({
  id: z.number(),
  email: z.string().email(),
  name: z.string(),
  status: userStatusSchema,
  externalUserId: z.string().nullable(),
  employeeCode: z.string().nullable(),
  emailConfirmed: z.boolean(),
  lastLoginAt: z.string().nullable(),
  createdAt: z.string(),
  roleName: z.string().nullable().optional(),
});

export type User = z.infer<typeof userSchema>;
